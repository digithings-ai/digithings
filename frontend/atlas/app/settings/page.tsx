'use client';

import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import { SettingsContent } from '@/components/settings-content';

export default function SettingsPage() {
  return (
    <div className={`${SUBPAGE_MAX} py-6 md:py-8`}>
      <h1 className="text-xl font-semibold text-text-primary mb-6">Settings</h1>
      <div className="glass-card p-6 max-w-md">
        <SettingsContent />
      </div>
    </div>
  );
}
