"use client";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LANGUAGES, resolveLanguageCode } from "@/lib/languages";

export function LanguageSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (code: string) => void;
}) {
  const current = LANGUAGES.find((l) => l.code === resolveLanguageCode(value)) ?? LANGUAGES[0]!;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger aria-label={`Response language: ${current.label}`}>
        {current.label}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {LANGUAGES.map((lang) => (
          <DropdownMenuItem key={lang.code} onClick={() => onChange(lang.code)}>
            {lang.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
