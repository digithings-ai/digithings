'use client';

import { LoginScreen } from '@/components/login-screen';

/** Static-export sign-up page — same PKCE card as login, create-account mode. */
export default function SignupPage() {
  return <LoginScreen initialMode="signup" />;
}
