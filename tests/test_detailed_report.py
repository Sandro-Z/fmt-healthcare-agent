import json
from pathlib import Path
from wgs_agent.tools.detailed_report import build_detailed_report, collect_evidence, validate_reasoning, generate_figures


def make_report(**overrides):
    args = dict(sample_id="TEST", species_data={}, compare_data={}, enterotype_data={}, pathway_data={}, metabolite_data={}, drug_data={}, disease_data={}, knowledge_data={})
    args.update(overrides)
    return build_detailed_report(**args)


def test_missing_data_does_not_become_healthy_or_zero_measurement():
    text = make_report()
    assert "没有可用代谢物测量矩阵" in text
    assert "未提供实测蛋白组" in text
    assert "不能解释为无疾病或低风险" in text
    assert "综合健康评分:" not in text
    assert text.count("\n## ") == 13


def test_gene_family_is_not_protein_expression_and_zero_preserved():
    text = make_report(protein_data={"data_type":"gene_family", "gene_families":[{"gene_family":"UniRef90_TEST", "abundance":0, "unit":"CPM"}]})
    assert "UniRef90_TEST" in text and "| 0 | CPM |" in text
    assert "不等于蛋白质表达" in text


def test_evidence_ids_and_disease_counter_evidence():
    text = make_report(species_data={"species_list":[{"species":"Species A", "abundance":1.25}]}, disease_data={"diseases":[{"disease":"D", "risk_score":60, "details":[{"species":"Species A","status":"low","direction":"高","evidence":"source not verified"}]}]})
    assert "S1: Species A" in text and "D1: D" in text
    assert "source not verified" in text
    assert "未提供–未提供" in text


def test_reasoning_rejects_unknown_ids_and_fabricated_quotes():
    evidence={"S1":{"species":"Species A"}, "R1":{"conclusion":"functional potential only"}}
    good={"interpretation":"一种待验证解释", "evidence_ids":["S1","R1"], "support_quotes":[{"id":"S1","quote":"Species A"},{"id":"R1","quote":"functional potential"}], "limitations":"没有实测", "verification":"测定"}
    assert len(validate_reasoning(json.dumps({"statements":[good]}),evidence)["accepted"]) == 1
    good["support_quotes"][0]["quote"]="Species B"
    assert not validate_reasoning(json.dumps({"statements":[good]}),evidence)["accepted"]
    assert not validate_reasoning("疾病概率90%",evidence)["accepted"]


def test_figures_use_only_actual_finite_values(tmp_path):
    e={"S1":{"species":"A","abundance":1},"S2":{"species":"B","abundance":float('nan')}}
    output=generate_figures(str(tmp_path),"TEST",e)
    assert output["species"]["evidence_ids"]==["S1"]
    assert Path(output["species"]["path"]).is_file()
    assert "diseases" not in output


def test_pairing_descriptive_contribution_and_probability_boundary():
    text=make_report(fmt_matching_data={"status":"ok","model_name":"fmt-triplet-contrastive","top_k_matches":[{"donor_id":"D1","score":.8,"distance":2,"species_comparison":[{"species":"A","query":1,"donor":2,"difference":1}]}]})
    assert "exp(-d/" in text and "不是临床成功概率" in text
    assert "不能等同于模型贡献" in text
    assert "| A | 1 | 2 | 1 |" in text


def test_gene_family_loader_keeps_unstratified_records_only(tmp_path):
    from wgs_agent.tools.detailed_report import load_gene_family_evidence
    (tmp_path/'TEST_genefamilies_relab.tsv').write_text('# family\tsample\nUNMAPPED\t0.5\nUniRef90_A\t0.2\nUniRef90_A|s__A\t0.1\nUniRef90_B\t0\n')
    result=load_gene_family_evidence('TEST',tmp_path)
    assert result['n_total']==2
    assert result['data_type']=='metagenomic_gene_family'
    assert result['gene_families'][1]['abundance']==0


def test_report_model_respects_workspace_and_disable(tmp_path, monkeypatch):
    from wgs_agent.tools.detailed_report import resolve_report_model
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'model_service':{'provider':'local','base_url':'http://127.0.0.1:11434/v1','local_model':'test-local'}}))
    monkeypatch.delenv('WGS_REPORT_LLM_DISABLED', raising=False)
    monkeypatch.setenv('DEEPSEEK_API_KEY','legacy-test')
    assert resolve_report_model(path)['model']=='test-local'
    monkeypatch.setenv('WGS_REPORT_LLM_DISABLED','1')
    assert resolve_report_model(path) is None


def test_report_figure_restricts_sample_and_resolved_directory(tmp_path, monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app import main
    root=tmp_path/'results';(root/'figures').mkdir(parents=True)
    monkeypatch.setattr(main,'RESULTS_DIR',root)
    (root/'figures'/'TEST_species.png').write_bytes(b'test')
    assert main.report_figure('TEST','TEST_species.png').media_type=='image/png'
    for name in ('OTHER_species.png','../TEST_species.png'):
        with pytest.raises(HTTPException):
            main.report_figure('TEST',name)
    outside=tmp_path/'outside.png';outside.write_bytes(b'test')
    (root/'figures'/'TEST_outside.png').symlink_to(outside)
    with pytest.raises(HTTPException):
        main.report_figure('TEST','TEST_outside.png')
