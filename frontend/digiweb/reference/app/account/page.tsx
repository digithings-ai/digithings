import "./account.css";

import { AuthCardProposals } from "@/components/account/auth-card-proposals";
import { LoginCard } from "@/components/account/login-card";
import { PaymentBand } from "@/components/account/payment-band";
import { ProfileCard } from "@/components/account/profile-card";
import { SessionCard } from "@/components/account/session-card";
import { SettingsPanel } from "@/components/account/settings-panel";
import { SignupCard } from "@/components/account/signup-card";

export default function AccountPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// account"}</p>
        <h1>
          Account surfaces, <em>end to end.</em>
        </h1>
        <p>
          Login, sign-up, session/logout, payment, settings, and profile templates — the
          transactional pages every product surface eventually needs. Olympus OAuth and
          tier-hidden settings tabs live here first.
        </p>
      </header>

      <AuthCardProposals />
      <LoginCard />
      <SignupCard />
      <SessionCard />
      <PaymentBand />
      <SettingsPanel />
      <ProfileCard />
    </main>
  );
}
