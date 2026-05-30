import Link from "next/link";
import WaitlistForm from "./WaitlistForm";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export const metadata = {
  title: "Reeva — Meet Your New Receptionist",
  description: "AI receptionist that answers your calls, books appointments, and never misses a lead.",
};

const css = `
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
          --ink: #1a1814; --ink2: #4a4540; --ink3: #9a9590;
          --bg: #faf8f4; --bg2: #f0ece4; --bg3: #e8e2d8;
          --reeva: #e8622a; --reeva-light: #fdf0ea; --reeva-mid: #f4a07a;
          --green: #2a6b4a; --green-light: #e8f5ee; --white: #ffffff;
          --serif: 'Fraunces', Georgia, serif;
          --sans: 'Plus Jakarta Sans', system-ui, sans-serif;
          --r: 14px; --r-lg: 24px;
        }
        html { scroll-behavior: smooth; }
        body { font-family: var(--sans); background: var(--bg); color: var(--ink); line-height: 1.6; overflow-x: hidden; }

        nav { position: fixed; top: 0; left: 0; right: 0; z-index: 100; display: flex; align-items: center; justify-content: space-between; padding: 1rem 2.5rem; background: rgba(250,248,244,0.9); backdrop-filter: blur(16px); border-bottom: 1px solid var(--bg3); }
        .logo { display: flex; align-items: center; gap: 10px; text-decoration: none; }
        .logo-mark { width: 32px; height: 32px; border-radius: 10px; background: var(--reeva); display: flex; align-items: center; justify-content: center; font-family: var(--serif); font-size: 17px; font-weight: 400; color: white; font-style: italic; }
        .logo-name { font-family: var(--serif); font-size: 22px; font-weight: 300; color: var(--ink); letter-spacing: -.01em; }
        .nav-links { display: flex; align-items: center; gap: 2rem; }
        .nav-links a { font-size: 14px; color: var(--ink2); text-decoration: none; font-weight: 400; transition: color .2s; }
        .nav-links a:hover { color: var(--ink); }
        .nav-cta { background: var(--reeva); color: white; font-size: 14px; font-weight: 500; padding: 9px 22px; border-radius: 99px; text-decoration: none; transition: all .2s; }
        .nav-cta:hover { background: #d04f1e; transform: translateY(-1px); }
        .nav-signin { font-size: 14px; color: var(--ink2); text-decoration: none; font-weight: 400; transition: color .2s; }
        .nav-signin:hover { color: var(--ink); }

        .hero { min-height: 100vh; display: grid; grid-template-columns: 1fr 1fr; align-items: center; gap: 4rem; padding: 8rem 5rem 5rem; max-width: 1200px; margin: 0 auto; position: relative; }
        .hero-left { position: relative; z-index: 1; }
        .hero-tag { display: inline-flex; align-items: center; gap: 8px; background: var(--reeva-light); color: var(--reeva); font-size: 13px; font-weight: 500; padding: 6px 14px; border-radius: 99px; margin-bottom: 1.75rem; animation: up .6s ease both; }
        .tag-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--reeva); animation: blink 2s ease infinite; }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
        .hero h1 { font-family: var(--serif); font-size: clamp(2.8rem, 5vw, 4.5rem); font-weight: 300; line-height: 1.1; color: var(--ink); margin-bottom: 1.5rem; animation: up .7s .08s ease both; }
        .hero h1 em { font-style: italic; color: var(--reeva); }
        .hero h1 span { display: block; }
        .hero-sub { font-size: 17px; color: var(--ink2); font-weight: 300; line-height: 1.7; max-width: 440px; margin-bottom: 2.5rem; animation: up .7s .16s ease both; }
        .hero-sub strong { color: var(--ink); font-weight: 500; }
        .hero-actions { display: flex; align-items: center; gap: 1rem; animation: up .7s .24s ease both; }
        .btn-main { background: var(--reeva); color: white; padding: 14px 28px; border-radius: 99px; font-size: 15px; font-weight: 500; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; transition: all .2s; }
        .btn-main:hover { background: #d04f1e; transform: translateY(-2px); }
        .btn-ghost { color: var(--ink2); font-size: 14px; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; transition: color .2s; }
        .btn-ghost:hover { color: var(--ink); }

        .hero-right { animation: up .8s .3s ease both; position: relative; }
        .reeva-card { background: var(--white); border: 1px solid var(--bg3); border-radius: var(--r-lg); overflow: hidden; box-shadow: 0 8px 60px rgba(26,24,20,0.1); }
        .reeva-topbar { background: var(--reeva); padding: 1rem 1.25rem; display: flex; align-items: center; gap: 10px; }
        .reeva-avatar { width: 36px; height: 36px; border-radius: 50%; background: rgba(255,255,255,0.25); display: flex; align-items: center; justify-content: center; font-family: var(--serif); font-size: 16px; color: white; font-style: italic; }
        .reeva-info { flex: 1; }
        .reeva-name { font-size: 14px; font-weight: 500; color: white; }
        .reeva-status { font-size: 12px; color: rgba(255,255,255,0.7); display: flex; align-items: center; gap: 5px; }
        .status-dot { width: 6px; height: 6px; border-radius: 50%; background: #7fffb8; animation: blink 1.5s ease infinite; }
        .reeva-timer { font-size: 13px; color: rgba(255,255,255,0.8); font-weight: 500; }
        .chat-body { padding: 1.25rem; display: flex; flex-direction: column; gap: 12px; }
        .msg { display: flex; flex-direction: column; gap: 3px; }
        .msg-label { font-size: 11px; color: var(--ink3); font-weight: 500; letter-spacing: .03em; }
        .msg-label.right { text-align: right; }
        .bubble { font-size: 14px; line-height: 1.55; padding: 10px 14px; border-radius: 16px; max-width: 85%; }
        .bubble-reeva { background: var(--bg); color: var(--ink); border-radius: 4px 16px 16px 16px; }
        .bubble-caller { background: var(--ink); color: var(--bg); border-radius: 16px 16px 4px 16px; align-self: flex-end; }
        .booking-confirm { margin: 0 1.25rem 1.25rem; background: var(--green-light); border: 1px solid rgba(42,107,74,0.15); border-radius: var(--r); padding: 12px 14px; display: flex; align-items: flex-start; gap: 10px; }
        .confirm-icon { width: 20px; height: 20px; border-radius: 50%; background: var(--green); display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px; }
        .confirm-icon svg { width: 11px; height: 11px; stroke: white; fill: none; stroke-width: 2.5; }
        .confirm-text { font-size: 13px; color: var(--green); line-height: 1.5; }
        .confirm-text strong { display: block; font-weight: 500; margin-bottom: 1px; }
        .floating-note { position: absolute; bottom: -16px; right: -16px; background: var(--white); border: 1px solid var(--bg3); border-radius: var(--r); padding: 10px 14px; box-shadow: 0 4px 20px rgba(26,24,20,0.08); font-size: 13px; color: var(--ink2); white-space: nowrap; display: flex; align-items: center; gap: 8px; }
        .floating-note strong { color: var(--ink); }
        @keyframes up { from { opacity:0; transform:translateY(18px); } to { opacity:1; transform:translateY(0); } }

        .intro-strip { background: var(--ink); padding: 1.25rem 5rem; display: flex; align-items: center; justify-content: center; gap: 3.5rem; flex-wrap: wrap; }
        .strip-stat { text-align: center; }
        .strip-num { font-family: var(--serif); font-size: 2rem; font-weight: 300; color: var(--reeva-mid); display: block; line-height: 1; }
        .strip-label { font-size: 12px; color: rgba(250,248,244,0.45); margin-top: 3px; }

        section { padding: 6rem 5rem; }
        .container { max-width: 1100px; margin: 0 auto; }
        .eyebrow { font-size: 12px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: var(--reeva); margin-bottom: .875rem; }
        .s-title { font-family: var(--serif); font-size: clamp(2rem, 3.5vw, 2.8rem); font-weight: 300; line-height: 1.2; color: var(--ink); margin-bottom: .875rem; }
        .s-title em { font-style: italic; }
        .s-sub { font-size: 16px; color: var(--ink2); font-weight: 300; line-height: 1.7; max-width: 520px; }

        .meet { background: var(--bg); }
        .meet-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5rem; align-items: center; margin-top: 3.5rem; }
        .trait-list { list-style: none; display: flex; flex-direction: column; gap: 1.25rem; margin-top: 2rem; }
        .trait { display: flex; gap: 14px; align-items: flex-start; }
        .trait-icon { width: 38px; height: 38px; border-radius: 10px; flex-shrink: 0; background: var(--reeva-light); display: flex; align-items: center; justify-content: center; }
        .trait-icon svg { width: 18px; height: 18px; stroke: var(--reeva); fill: none; stroke-width: 1.5; }
        .trait-title { font-size: 15px; font-weight: 500; color: var(--ink); margin-bottom: 3px; }
        .trait-desc { font-size: 14px; color: var(--ink3); line-height: 1.55; }
        .reeva-quote { background: var(--reeva-light); border-radius: var(--r-lg); padding: 2rem; position: relative; margin-bottom: 1.5rem; }
        .reeva-quote::before { content: '“'; font-family: var(--serif); font-size: 6rem; font-weight: 300; color: var(--reeva-mid); position: absolute; top: -1rem; left: 1.25rem; line-height: 1; pointer-events: none; }
        .reeva-quote p { font-family: var(--serif); font-size: 1.2rem; font-style: italic; font-weight: 300; color: var(--ink); line-height: 1.6; padding-top: .75rem; }
        .reeva-sig { font-size: 13px; color: var(--reeva); font-weight: 500; margin-top: 1rem; display: flex; align-items: center; gap: 6px; }
        .reeva-sig::before { content: ''; display: block; width: 20px; height: 1px; background: var(--reeva); }
        .stat-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .mini-stat { background: var(--white); border: 1px solid var(--bg3); border-radius: var(--r); padding: 1.25rem; }
        .mini-num { font-family: var(--serif); font-size: 2.2rem; font-weight: 300; color: var(--ink); line-height: 1; }
        .mini-label { font-size: 13px; color: var(--ink3); margin-top: 4px; line-height: 1.4; }

        .how { background: var(--bg2); }
        .steps-row { display: grid; grid-template-columns: repeat(4,1fr); gap: 1.5rem; margin-top: 3.5rem; }
        .step-card { background: var(--white); border: 1px solid var(--bg3); border-radius: var(--r-lg); padding: 1.75rem; }
        .step-n { font-family: var(--serif); font-size: 2.5rem; font-weight: 300; color: var(--bg3); line-height: 1; margin-bottom: 1rem; }
        .step-title { font-size: 15px; font-weight: 500; color: var(--ink); margin-bottom: .5rem; }
        .step-body { font-size: 13px; color: var(--ink3); line-height: 1.6; }
        .step-tag { display: inline-block; margin-top: .875rem; background: var(--reeva-light); color: var(--reeva); font-size: 11px; font-weight: 500; padding: 3px 10px; border-radius: 99px; }

        .handles { background: var(--bg); }
        .handles-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 1.25rem; margin-top: 3.5rem; }
        .handle-card { background: var(--white); border: 1px solid var(--bg3); border-radius: var(--r-lg); padding: 1.75rem; transition: all .2s; }
        .handle-card:hover { transform: translateY(-3px); box-shadow: 0 8px 32px rgba(26,24,20,0.07); }
        .handle-emoji { font-size: 28px; margin-bottom: 1rem; display: block; }
        .handle-title { font-size: 15px; font-weight: 500; color: var(--ink); margin-bottom: .5rem; }
        .handle-desc { font-size: 14px; color: var(--ink3); line-height: 1.6; }

        .industries { background: var(--ink); padding: 4rem 5rem; text-align: center; }
        .industries .eyebrow { color: var(--reeva-mid); }
        .industries .s-title { color: var(--bg); margin: 0 auto 2.5rem; text-align: center; }
        .pill-grid { display: flex; flex-wrap: wrap; gap: .75rem; justify-content: center; max-width: 700px; margin: 0 auto; }
        .pill { background: rgba(250,248,244,0.07); border: 1px solid rgba(250,248,244,0.12); color: rgba(250,248,244,0.65); font-size: 14px; font-weight: 400; padding: 8px 18px; border-radius: 99px; transition: all .2s; cursor: default; }
        .pill:hover { background: var(--reeva-light); color: var(--reeva); border-color: transparent; }

        .pricing { background: var(--bg); }
        .pricing-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 1.25rem; margin-top: 3.5rem; align-items: start; }
        .p-card { background: var(--white); border: 1px solid var(--bg3); border-radius: var(--r-lg); padding: 2rem; }
        .p-card.pop { background: var(--reeva); border-color: var(--reeva); }
        .p-name { font-size: 12px; font-weight: 500; letter-spacing: .07em; text-transform: uppercase; color: var(--ink3); margin-bottom: .75rem; }
        .p-card.pop .p-name { color: rgba(255,255,255,0.6); }
        .p-price { font-family: var(--serif); font-size: 3.5rem; font-weight: 300; color: var(--ink); line-height: 1; }
        .p-card.pop .p-price { color: white; }
        .p-mo { font-size: 14px; color: var(--ink3); margin-bottom: 1rem; }
        .p-card.pop .p-mo { color: rgba(255,255,255,0.55); }
        .p-tagline { font-size: 14px; color: var(--ink2); font-weight: 300; line-height: 1.55; margin-bottom: 1.5rem; }
        .p-card.pop .p-tagline { color: rgba(255,255,255,0.7); }
        .p-divider { height: 1px; background: var(--bg2); margin-bottom: 1.5rem; }
        .p-card.pop .p-divider { background: rgba(255,255,255,0.15); }
        .p-list { list-style: none; display: flex; flex-direction: column; gap: 10px; margin-bottom: 2rem; }
        .p-item { display: flex; align-items: flex-start; gap: 8px; font-size: 14px; color: var(--ink2); }
        .p-card.pop .p-item { color: rgba(255,255,255,0.8); }
        .p-check { width: 16px; height: 16px; stroke: var(--green); fill: none; stroke-width: 2.5; flex-shrink: 0; margin-top: 2px; }
        .p-card.pop .p-check { stroke: rgba(255,255,255,0.8); }
        .p-btn { display: block; text-align: center; padding: 12px; border-radius: 99px; font-size: 14px; font-weight: 500; text-decoration: none; transition: all .2s; border: 1.5px solid var(--bg3); color: var(--ink); }
        .p-btn:hover { border-color: var(--ink); }
        .p-card.pop .p-btn { background: white; border-color: white; color: var(--reeva); }
        .p-card.pop .p-btn:hover { background: rgba(255,255,255,0.9); }
        .pop-badge { background: white; color: var(--reeva); font-size: 11px; font-weight: 500; padding: 3px 12px; border-radius: 99px; display: inline-block; margin-bottom: 1rem; }

        .cta { background: var(--bg2); padding: 6rem 5rem; }
        .cta-inner { max-width: 640px; margin: 0 auto; text-align: center; background: var(--white); border: 1px solid var(--bg3); border-radius: var(--r-lg); padding: 3.5rem; }
        .cta-emoji { font-size: 2.5rem; display: block; margin-bottom: 1.25rem; }
        .cta-inner h2 { font-family: var(--serif); font-size: 2.2rem; font-weight: 300; color: var(--ink); margin-bottom: .875rem; line-height: 1.2; }
        .cta-inner h2 em { font-style: italic; color: var(--reeva); }
        .cta-inner p { font-size: 16px; color: var(--ink2); font-weight: 300; margin-bottom: 2rem; line-height: 1.65; }
        .cta-note { font-size: 12px; color: var(--ink3); }

        footer { background: var(--ink); padding: 2rem 5rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem; }
        .footer-logo { font-family: var(--serif); font-size: 20px; font-weight: 300; font-style: italic; color: rgba(250,248,244,0.5); }
        .footer-links { display: flex; gap: 1.5rem; }
        .footer-links a { font-size: 13px; color: rgba(250,248,244,0.35); text-decoration: none; transition: color .2s; }
        .footer-links a:hover { color: rgba(250,248,244,0.7); }

        @media (max-width: 900px) {
          .hero { grid-template-columns: 1fr; padding: 7rem 2rem 3rem; }
          .hero-right { display: none; }
          section { padding: 4rem 1.5rem; }
          .meet-grid { grid-template-columns: 1fr; gap: 2.5rem; }
          .steps-row { grid-template-columns: 1fr 1fr; }
          .handles-grid { grid-template-columns: 1fr; }
          .pricing-grid { grid-template-columns: 1fr; }
          .intro-strip { padding: 1.25rem 2rem; gap: 2rem; }
          .industries { padding: 4rem 1.5rem; }
          nav { padding: 1rem 1.25rem; }
          .nav-links { display: none; }
          footer { padding: 2rem 1.5rem; }
          .cta { padding: 4rem 1.5rem; }
          .cta-inner { padding: 2rem 1.5rem; }
        }
`;

export default function LandingPage() {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: css }} />

      {/* NAV */}
      <nav>
        <a className="logo" href="#">
          <span className="logo-mark">R</span>
          <span className="logo-name">Reeva</span>
        </a>
        <div className="nav-links">
          <a href="#meet">Meet Reeva</a>
          <a href="#how">How it works</a>
          <a href="#demo">Demo</a>
          <a href="#pricing">Pricing</a>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <Link href="/signin" className="nav-signin">Sign in</Link>
          <a href={`${BASE}/api/auth/google/start?mode=signup`} className="nav-cta">Sign up</a>
        </div>
      </nav>

      {/* HERO */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 2.5rem" }}>
        <div className="hero" style={{ paddingLeft: 0, paddingRight: 0 }}>
          <div className="hero-left">
            <div className="hero-tag">
              <span className="tag-dot" />
              Now in early access
            </div>
            <h1>
              <span>Hi, I&apos;m Reeva.</span>
              <span>I answer your <em>calls</em></span>
              <span>so you don&apos;t have to.</span>
            </h1>
            <p className="hero-sub">
              I&apos;m your AI receptionist — <strong>friendly, reliable, and always on</strong>. I book appointments, answer questions, and make sure every caller feels taken care of. Even at 11pm on a Sunday.
            </p>
            <div className="hero-actions">
              <a href={`${BASE}/api/auth/google/start?mode=signup`} className="btn-main">
                Sign up free
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
              </a>
              <a href="#how" className="btn-ghost">
                See how I work
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 9l-7 7-7-7"/></svg>
              </a>
            </div>
          </div>
          <div className="hero-right">
            <div className="reeva-card">
              <div className="reeva-topbar">
                <div className="reeva-avatar">R</div>
                <div className="reeva-info">
                  <div className="reeva-name">Reeva</div>
                  <div className="reeva-status"><span className="status-dot" /> On a call right now</div>
                </div>
                <div className="reeva-timer">0:38</div>
              </div>
              <div className="chat-body">
                <div className="msg">
                  <span className="msg-label">Reeva</span>
                  <div className="bubble bubble-reeva">Hi! Thanks for calling Bright Smile Dental. This is Reeva — how can I help you today?</div>
                </div>
                <div className="msg">
                  <span className="msg-label right">Caller</span>
                  <div className="bubble bubble-caller">Hey, I&apos;d like to book a cleaning. Do you have anything Tuesday?</div>
                </div>
                <div className="msg">
                  <span className="msg-label">Reeva</span>
                  <div className="bubble bubble-reeva">Tuesday works great! I have 10am or 2pm open. Which do you prefer?</div>
                </div>
                <div className="msg">
                  <span className="msg-label right">Caller</span>
                  <div className="bubble bubble-caller">2pm please. Name&apos;s Sarah.</div>
                </div>
                <div className="msg">
                  <span className="msg-label">Reeva</span>
                  <div className="bubble bubble-reeva">Perfect, Sarah! I&apos;ve got you booked for Tuesday at 2pm. You&apos;ll get a confirmation text shortly. See you then!</div>
                </div>
              </div>
              <div className="booking-confirm">
                <div className="confirm-icon">
                  <svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
                <div className="confirm-text">
                  <strong>Appointment booked</strong>
                  Sarah — Tuesday 2:00pm · Added to Google Calendar
                </div>
              </div>
            </div>
            <div className="floating-note">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--reeva)" strokeWidth="2"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.81 19.79 19.79 0 01.12 1.2 2 2 0 012.11 0h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg>
              <span>Reeva also handled <strong>11 other calls</strong> today</span>
            </div>
          </div>
        </div>
      </div>

      {/* STRIP */}
      <div className="intro-strip">
        <div className="strip-stat"><span className="strip-num">62%</span><span className="strip-label">of SMB calls go unanswered</span></div>
        <div className="strip-stat"><span className="strip-num">24/7</span><span className="strip-label">Reeva never clocks out</span></div>
        <div className="strip-stat"><span className="strip-num">&lt; 3s</span><span className="strip-label">to answer every call</span></div>
        <div className="strip-stat"><span className="strip-num">$0</span><span className="strip-label">setup fee, ever</span></div>
      </div>

      {/* MEET REEVA */}
      <section className="meet" id="meet">
        <div className="container">
          <div className="eyebrow">Meet Reeva</div>
          <h2 className="s-title">She&apos;s not a bot.<br />She&apos;s your <em>best hire</em>.</h2>
          <p className="s-sub">Reeva sounds like a person, thinks like a pro, and never has a bad day. Here&apos;s what makes her different.</p>
          <div className="meet-grid">
            <div>
              <ul className="trait-list">
                {[
                  { icon: <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" strokeLinecap="round" strokeLinejoin="round"/>, title: "Genuinely warm", desc: "Reeva doesn't read from a script. She has a personality — friendly, unhurried, human. Callers feel heard, not processed." },
                  { icon: <><circle cx="12" cy="12" r="10" strokeLinecap="round" strokeLinejoin="round"/><polyline points="12 6 12 12 16 14" strokeLinecap="round" strokeLinejoin="round"/></>, title: "Always available", desc: "Early mornings, late nights, weekends. Reeva picks up every single time without overtime, sick days, or complaints." },
                  { icon: <><path d="M9 11l3 3L22 4" strokeLinecap="round" strokeLinejoin="round"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" strokeLinecap="round" strokeLinejoin="round"/></>, title: "Actually books things", desc: "Not just messages — real appointments, in your real calendar, confirmed before the caller hangs up." },
                  { icon: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" strokeLinecap="round" strokeLinejoin="round"/>, title: "Knows when to hand off", desc: "Complex situation? Upset caller? Reeva transfers to you immediately — with a full summary of what was said." },
                ].map((t) => (
                  <li className="trait" key={t.title}>
                    <div className="trait-icon"><svg viewBox="0 0 24 24">{t.icon}</svg></div>
                    <div>
                      <div className="trait-title">{t.title}</div>
                      <div className="trait-desc">{t.desc}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <div className="reeva-quote">
                <p>Hey there! I can help you book an appointment, answer questions about our services, or take a message for the team. What can I do for you today?</p>
                <div className="reeva-sig">Reeva, answering right now</div>
              </div>
              <div className="stat-pair">
                {[["85%","of voicemail callers never call back"],["5 min","to set Reeva up and go live"],["$45K","saved vs. a full-time receptionist"],["300%","avg ROI in the first year"]].map(([n,l]) => (
                  <div className="mini-stat" key={l}><div className="mini-num">{n}</div><div className="mini-label">{l}</div></div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="how" id="how">
        <div className="container">
          <div className="eyebrow">How it works</div>
          <h2 className="s-title">Get Reeva answering calls<br />in <em>under five minutes</em></h2>
          <p className="s-sub">No IT department needed. No complicated setup. Just tell Reeva about your business and she&apos;s ready to go.</p>
          <div className="steps-row">
            {[
              { n: "01", title: "Tell Reeva about your business", body: "Your name, hours, services, and the questions you get asked every day. The more she knows, the better she sounds.", tag: "2 minutes" },
              { n: "02", title: "Forward your calls to Reeva", body: "Point your existing phone number to Reeva. No new number, no hardware, no tech skills required.", tag: "60 seconds" },
              { n: "03", title: "Connect your calendar", body: "Link Google Calendar and Reeva books real appointments — checking availability and confirming before hanging up.", tag: "1 click" },
              { n: "04", title: "Watch your dashboard", body: "See every call, every booking, every missed opportunity — recovered. You stay in control without answering every call yourself.", tag: "You're live" },
            ].map((s) => (
              <div className="step-card" key={s.n}>
                <div className="step-n">{s.n}</div>
                <div className="step-title">{s.title}</div>
                <div className="step-body">{s.body}</div>
                <span className="step-tag">{s.tag}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* WHAT REEVA HANDLES */}
      <section className="handles">
        <div className="container">
          <div className="eyebrow">What Reeva handles</div>
          <h2 className="s-title">Everything your front desk does,<br /><em>on autopilot</em></h2>
          <div className="handles-grid">
            {[
              { emoji: "📅", title: "Books appointments", desc: "Checks your real calendar, finds open slots, and confirms the booking before the call ends. No double-booking, ever." },
              { emoji: "💬", title: "Answers your FAQs", desc: "Hours, location, services, pricing, parking — Reeva knows your business and answers confidently, every time." },
              { emoji: "📞", title: "Takes callback requests", desc: "When someone just needs a call back, Reeva collects their name and number and logs it straight to your dashboard." },
              { emoji: "🔀", title: "Transfers complex calls", desc: "When a human is needed, Reeva hands off gracefully — with a summary so you're never starting from scratch." },
              { emoji: "🌙", title: "Covers after hours", desc: "15–20% of bookings happen outside business hours. Reeva captures every single one, even at midnight." },
              { emoji: "🗂️", title: "Logs everything", desc: "Every call, every intent, every outcome. Your dashboard gives you a clear picture of who's calling and why." },
            ].map((h) => (
              <div className="handle-card" key={h.title}>
                <span className="handle-emoji">{h.emoji}</span>
                <div className="handle-title">{h.title}</div>
                <div className="handle-desc">{h.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* INDUSTRIES */}
      <div className="industries">
        <div className="eyebrow">Who Reeva works for</div>
        <h2 className="s-title">If your phone rings,<br /><em>Reeva&apos;s got it</em></h2>
        <div className="pill-grid">
          {["Dental practices","Hair salons","Law firms","Plumbers","HVAC companies","Chiropractors","Med spas","Veterinarians","Auto repair","Accountants","Physical therapy","Cleaning services"].map((p) => (
            <span className="pill" key={p}>{p}</span>
          ))}
        </div>
      </div>

      {/* DEMO */}
      <section id="demo" style={{ background: "var(--bg2)", padding: "5rem 0" }}>
        <div className="container" style={{ maxWidth: 680, textAlign: "center" }}>
          <div className="eyebrow">Live demo</div>
          <h2 className="s-title" style={{ marginBottom: "1rem" }}>
            Hear Reeva in action — <em>right now</em>
          </h2>
          <p style={{ fontSize: "1.0625rem", color: "var(--ink2)", lineHeight: 1.6, marginBottom: "2.5rem" }}>
            Call the number below and talk to a live AI receptionist for Bright Smile Dental.
            No app, no sign-up — just pick up the phone.
          </p>

          {/* Phone number card */}
          <div style={{
            display: "inline-flex", flexDirection: "column", alignItems: "center",
            background: "var(--white)", border: "1.5px solid var(--bg3)",
            borderRadius: "var(--r-lg)", padding: "2rem 3rem",
            boxShadow: "0 2px 12px rgba(0,0,0,0.06)", marginBottom: "2rem",
          }}>
            <div style={{ fontSize: "0.75rem", fontWeight: 600, letterSpacing: "0.08em", color: "var(--ink3)", textTransform: "uppercase", marginBottom: "0.5rem" }}>
              Demo number
            </div>
            <a
              href={`tel:${process.env.NEXT_PUBLIC_DEMO_PHONE_NUMBER || ""}`}
              style={{ fontSize: "2rem", fontWeight: 700, color: "var(--ink)", letterSpacing: "0.02em", textDecoration: "none", fontFamily: "var(--serif)" }}
            >
              {process.env.NEXT_PUBLIC_DEMO_PHONE_NUMBER || "Coming soon"}
            </a>
          </div>

          {/* Suggested prompts */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.625rem", justifyContent: "center", marginBottom: "1.5rem" }}>
            {[
              "What are your hours?",
              "Can I book an appointment?",
              "Where are you located?",
              "What services do you offer?",
            ].map((prompt) => (
              <span key={prompt} style={{
                background: "var(--white)", border: "1px solid var(--bg3)",
                borderRadius: 999, padding: "0.4rem 0.875rem",
                fontSize: "0.8125rem", color: "var(--ink2)",
              }}>
                &ldquo;{prompt}&rdquo;
              </span>
            ))}
          </div>

          <p style={{ fontSize: "0.8125rem", color: "var(--ink3)" }}>
            Demo calls are capped at a few minutes. Standard carrier rates apply.
          </p>
        </div>
      </section>

      {/* PRICING */}
      <section className="pricing" id="pricing">
        <div className="container">
          <div className="eyebrow">Pricing</div>
          <h2 className="s-title">One missed appointment pays<br />for Reeva&apos;s <em>entire month</em></h2>
          <p className="s-sub">Flat-rate, no surprises. No per-minute charges. No setup fees. Cancel anytime.</p>
          <div className="pricing-grid">
            <div className="p-card">
              <div className="p-name">Starter</div>
              <div className="p-price">$99</div>
              <div className="p-mo">/month</div>
              <div className="p-tagline">Perfect for solo operators just getting started with Reeva.</div>
              <div className="p-divider" />
              <ul className="p-list">
                {["Up to 200 calls/month","Appointment booking","Google Calendar sync","Dashboard & call logs","1 business profile"].map((f) => (
                  <li className="p-item" key={f}><svg className="p-check" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>{f}</li>
                ))}
              </ul>
              <a href={`${BASE}/api/auth/google/start?mode=signup`} className="p-btn">Get started</a>
            </div>
            <div className="p-card pop">
              <div className="pop-badge">Most popular</div>
              <div className="p-name">Growth</div>
              <div className="p-price">$199</div>
              <div className="p-mo">/month</div>
              <div className="p-tagline">For businesses that can&apos;t afford to miss a single call, ever.</div>
              <div className="p-divider" />
              <ul className="p-list">
                {["Unlimited calls","Everything in Starter","Call transfer to your number","Advanced analytics","Priority support"].map((f) => (
                  <li className="p-item" key={f}><svg className="p-check" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>{f}</li>
                ))}
              </ul>
              <a href={`${BASE}/api/auth/google/start?mode=signup`} className="p-btn">Get started</a>
            </div>
            <div className="p-card">
              <div className="p-name">Multi-location</div>
              <div className="p-price">Custom</div>
              <div className="p-mo">&nbsp;</div>
              <div className="p-tagline">For franchises and multi-location businesses. Reeva scales with you.</div>
              <div className="p-divider" />
              <ul className="p-list">
                {["Multiple business profiles","Everything in Growth","CRM integrations","Dedicated onboarding","SLA guarantee"].map((f) => (
                  <li className="p-item" key={f}><svg className="p-check" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>{f}</li>
                ))}
              </ul>
              <a href="#waitlist" className="p-btn">&apos;Let&apos;s talk</a>
            </div>
          </div>
        </div>
      </section>

      {/* CTA / WAITLIST */}
      <section className="cta" id="waitlist">
        <div className="cta-inner">
          <span className="cta-emoji">👋</span>
          <h2>Ready to meet <em>Reeva?</em></h2>
          <p>Join the waitlist and get early access. First members get 3 months at half price — and Reeva will personally thank you. Well, almost.</p>
          <WaitlistForm />
          <p className="cta-note">No credit card. No commitment. Reeva won&apos;t spam you — she&apos;s too busy answering calls.</p>
        </div>
      </section>

      {/* FOOTER */}
      <footer>
        <span className="footer-logo">Reeva</span>
        <div className="footer-links">
          <a href="#">Privacy</a>
          <a href="#">Terms</a>
          <a href="#">Contact</a>
          <Link href="/signin" style={{ fontSize: 13, color: "rgba(250,248,244,0.35)", textDecoration: "none" }}>Sign in</Link>
        </div>
      </footer>
    </>
  );
}
