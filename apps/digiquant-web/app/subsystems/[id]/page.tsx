import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DocumentFrame, PageTitle, subsystemById, subsystems } from "@digithings/ui";

export const dynamicParams = false;
export function generateStaticParams() {
  return subsystems.map((s) => ({ id: s.id }));
}
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const s = subsystemById(id);
  return s ? { title: `${s.name} — digiquant`, description: s.tagline } : { title: "Subsystem — digiquant" };
}

export default async function SubsystemPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = subsystemById(id);
  if (!s) notFound();

  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <PageTitle title={s.name}>{s.tagline}</PageTitle>
      </DocumentFrame>
    </main>
  );
}
