import "./account.css";

import { LoginCard } from "@/components/account/login-card";
import { PaymentBand } from "@/components/account/payment-band";
import { ProfileCard } from "@/components/account/profile-card";
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
          Login, sign-up, payment, settings, and profile templates — the transactional pages that
          every product surface eventually needs.
        </p>
      </header>

      <LoginCard />
      <SignupCard />
      <PaymentBand />
      <SettingsPanel />
      <ProfileCard />
    </main>
  );
}
