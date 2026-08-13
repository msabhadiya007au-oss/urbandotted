import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errText } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2 } from "lucide-react";

export default function Login() {
  const { onAuthed } = useApp();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [f, setF] = useState({ email: "", password: "", name: "", business_name: "Urban Dotted" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const url = mode === "login" ? "/auth/login" : "/auth/register";
      const payload = mode === "login"
        ? { email: f.email, password: f.password }
        : { email: f.email, password: f.password, name: f.name, business_name: f.business_name };
      const { data } = await api.post(url, payload);
      await onAuthed(data);
      toast.success(mode === "login" ? "Welcome back" : "Account created");
      navigate("/dashboard");
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  };

  const google = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      {/* Left: brand panel */}
      <div className="hidden lg:flex flex-col justify-between bg-primary text-primary-foreground p-14">
        <div>
          <div className="font-serif text-4xl font-semibold">urban<span className="italic">dotted</span></div>
          <div className="overline mt-2 text-primary-foreground/60">Expense Book</div>
        </div>
        <div className="max-w-lg">
          <h1 className="font-serif text-5xl leading-[1.05] font-medium">
            Every dollar, every month,<br />ready for 30 June.
          </h1>
          <p className="mt-6 text-sm text-primary-foreground/70 leading-relaxed">
            Purpose-built bookkeeping for an Australian eCommerce business. Track expenses by category
            and subcategory, record Shopify revenue and refunds, keep GST per transaction, run a real
            COGS engine on landed inventory costs, and export accountant-ready records for any
            Australian financial year.
          </p>
          <div className="grid grid-cols-3 gap-px mt-10 border border-primary-foreground/15">
            {[["1 Jul – 30 Jun", "Financial year"], ["AUD", "Currency"], ["Adelaide", "Timezone"]].map(([v, l]) => (
              <div key={l} className="p-4 border border-primary-foreground/15">
                <div className="num text-sm font-semibold">{v}</div>
                <div className="overline mt-1 text-primary-foreground/50">{l}</div>
              </div>
            ))}
          </div>
        </div>
        <p className="text-[11px] text-primary-foreground/50 max-w-md">
          Bookkeeping and management software. Not a lodgement service — GST/BAS figures are estimates
          for your accountant or registered tax agent.
        </p>
      </div>

      {/* Right: form */}
      <div className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-sm">
          <div className="lg:hidden mb-8">
            <div className="font-serif text-3xl font-semibold text-primary">urban<span className="italic">dotted</span></div>
            <div className="overline mt-1">Expense Book</div>
          </div>

          <h2 className="font-serif text-3xl font-semibold">
            {mode === "login" ? "Sign in" : "Create your account"}
          </h2>
          <p className="text-sm text-muted-foreground mt-1.5">
            {mode === "login" ? "Access your financial records." : "Your business starts empty — load demo data any time."}
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4" data-testid="auth-form">
            {mode === "register" && (
              <>
                <div className="space-y-1.5">
                  <Label className="overline">Your name</Label>
                  <Input value={f.name} onChange={set("name")} required className="rounded-sm" data-testid="register-name" />
                </div>
                <div className="space-y-1.5">
                  <Label className="overline">Business name</Label>
                  <Input value={f.business_name} onChange={set("business_name")} required className="rounded-sm" data-testid="register-business" />
                </div>
              </>
            )}
            <div className="space-y-1.5">
              <Label className="overline">Email</Label>
              <Input type="email" value={f.email} onChange={set("email")} required autoComplete="email"
                className="rounded-sm" data-testid="login-email" />
            </div>
            <div className="space-y-1.5">
              <Label className="overline">Password</Label>
              <Input type="password" value={f.password} onChange={set("password")} required minLength={8}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                className="rounded-sm" data-testid="login-password" />
            </div>

            {error && (
              <p className="text-xs text-negative border-l-2 border-negative pl-2 py-1" data-testid="auth-error">{error}</p>
            )}

            <Button type="submit" disabled={busy} data-testid="auth-submit"
              className="w-full rounded-sm bg-primary text-primary-foreground hover:bg-primary/90 h-10">
              {busy ? <Loader2 className="animate-spin" size={15} /> : mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>

          <div className="flex items-center gap-3 my-5">
            <span className="h-px flex-1 bg-border" />
            <span className="overline">or</span>
            <span className="h-px flex-1 bg-border" />
          </div>

          <Button variant="outline" onClick={google} data-testid="google-login-btn"
            className="w-full rounded-sm h-10 border-border hover:bg-accent">
            Continue with Google
          </Button>

          <p className="text-xs text-muted-foreground mt-6 text-center">
            {mode === "login" ? "No account yet?" : "Already registered?"}{" "}
            <button type="button" data-testid="auth-toggle"
              onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
              className="text-foreground font-semibold underline underline-offset-2 hover:text-primary">
              {mode === "login" ? "Create one" : "Sign in"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

export function AuthCallback() {
  const { onAuthed } = useApp();
  const navigate = useNavigate();
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const hash = window.location.hash || "";
    const sessionId = new URLSearchParams(hash.replace(/^#/, "")).get("session_id");
    (async () => {
      try {
        const { data } = await api.post("/auth/session", { session_id: sessionId },
          { headers: { "X-Session-ID": sessionId } });
        window.history.replaceState(null, "", "/dashboard");
        await onAuthed(data);
        navigate("/dashboard", { replace: true });
      } catch (e) {
        toast.error(errText(e));
        window.history.replaceState(null, "", "/");
        navigate("/", { replace: true });
      }
    })();
  }, [onAuthed, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center text-muted-foreground gap-2">
      <Loader2 className="animate-spin" size={16} /> <span className="text-sm">Signing you in…</span>
    </div>
  );
}
