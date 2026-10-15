"use client";

import { Bot } from "lucide-react";
import { AuthAccess } from "@/components/auth-access";

export default function Home(){return <main className="login-page"><section className="login-shell"><header className="login-brand"><span><Bot size={22}/></span><div><strong>WGS·FMT Agent</strong><small>宏基因组智能分析平台</small></div></header><div className="login-welcome"><h1>欢迎使用</h1><p>登录后进入您的研究工作区</p></div><AuthAccess onSuccess={()=>window.location.assign("/chat")}/><footer>WGS·FMT Research Workspace</footer></section></main>}
