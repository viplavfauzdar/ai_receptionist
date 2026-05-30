const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Props {
  searchParams: { error?: string };
}

export const metadata = {
  title: "Sign in — Reeva",
};

export default function SignInPage({ searchParams }: Props) {
  const error = searchParams.error;

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "#faf8f4",
      fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
      padding: "1.5rem",
    }}>
      <div style={{
        background: "#ffffff",
        border: "1px solid #e8e2d8",
        borderRadius: "1rem",
        padding: "2.5rem 2rem",
        width: "100%",
        maxWidth: "380px",
        textAlign: "center",
      }}>
        {/* Logo */}
        <div style={{ marginBottom: "1.75rem" }}>
          <div style={{
            width: "44px",
            height: "44px",
            borderRadius: "12px",
            background: "#e8622a",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto 0.75rem",
            fontFamily: "Georgia, serif",
            fontSize: "22px",
            fontWeight: 300,
            color: "#fff",
            fontStyle: "italic",
          }}>R</div>
          <div style={{ fontSize: "20px", fontWeight: 600, color: "#1a1814" }}>Welcome to Reeva</div>
          <div style={{ fontSize: "14px", color: "#9a9590", marginTop: "0.35rem" }}>
            Sign in to manage your AI receptionist
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div style={{
            background: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: "0.5rem",
            padding: "0.75rem 1rem",
            fontSize: "13px",
            color: "#dc2626",
            marginBottom: "1.25rem",
            textAlign: "left",
          }}>
            {error === "missing_token" && "Something went wrong during sign-in. Please try again."}
            {error !== "missing_token" && "Sign-in failed. Please try again."}
          </div>
        )}

        {/* Sign in button — links to backend which redirects to Google */}
        <a
          href={`${BASE}/api/auth/google/start?mode=signin`}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.625rem",
            width: "100%",
            padding: "0.75rem 1rem",
            border: "1px solid #d1d5db",
            borderRadius: "0.5rem",
            background: "#ffffff",
            color: "#1a1814",
            fontSize: "15px",
            fontWeight: 500,
            textDecoration: "none",
            transition: "border-color 0.15s, box-shadow 0.15s",
            boxSizing: "border-box",
          }}
        >
          {/* Google logo */}
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M17.64 9.2045c0-.638-.0573-1.2518-.1636-1.8409H9v3.4814h4.8436c-.2086 1.125-.8427 2.0782-1.7959 2.7164v2.2581h2.9087c1.7018-1.5668 2.6836-3.874 2.6836-6.6149z" fill="#4285F4"/>
            <path d="M9 18c2.43 0 4.4673-.806 5.9564-2.1805l-2.9087-2.2581c-.8055.54-1.8364.8591-3.0477.8591-2.3441 0-4.3296-1.5836-5.0382-3.7105H.9574v2.3318C2.4382 15.9832 5.4818 18 9 18z" fill="#34A853"/>
            <path d="M3.9618 10.71c-.18-.54-.2823-1.1173-.2823-1.71s.1023-1.17.2823-1.71V4.9582H.9574C.3477 6.1732 0 7.5477 0 9s.3477 2.8268.9574 4.0418L3.9618 10.71z" fill="#FBBC05"/>
            <path d="M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.346l2.5813-2.5814C13.4632.8918 11.4259 0 9 0 5.4818 0 2.4382 2.0168.9574 4.9582L3.9618 7.29C4.6704 5.1632 6.6559 3.5795 9 3.5795z" fill="#EA4335"/>
          </svg>
          Continue with Google
        </a>

        <p style={{ fontSize: "12px", color: "#9a9590", marginTop: "1.25rem", lineHeight: 1.5 }}>
          New to Reeva? Signing in will create your account automatically.
        </p>

        <p style={{ fontSize: "12px", color: "#b0aaa4", marginTop: "1rem" }}>
          <a href="/" style={{ color: "#9a9590", textDecoration: "none" }}>← Back to home</a>
        </p>
      </div>
    </div>
  );
}
