import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DeskPage } from "@/components/desk/desk-page";
import { deskPathFromSlug, deskStaticParams } from "@/components/desk/paths";

export const dynamicParams = false;

export function generateStaticParams() {
  return deskStaticParams();
}

export const metadata: Metadata = {
  title: "Terminal — digiquant",
  description: "The digiquant terminal. Each block is one read of the official dashboard API.",
};

export default async function TerminalPage({ params }: { params: Promise<{ slug: string[] }> }) {
  const { slug } = await params;
  const path = deskPathFromSlug(slug);
  if (!path) notFound();
  return (
    <main id="main" className="h-[100svh]">
      <DeskPage key={path} path={path} />
    </main>
  );
}
