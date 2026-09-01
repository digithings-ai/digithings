'use client';

import { LoginScreen } from '@/components/login-screen';

/** Static-export login page — PKCE OAuth + email (no route handlers). */
export default function LoginPage() {
  return <LoginScreen />;
}
