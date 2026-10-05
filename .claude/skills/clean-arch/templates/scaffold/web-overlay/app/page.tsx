import { getHelloMessage } from "@/lib/backend";

export default async function Home() {
  const message = await getHelloMessage();

  return (
    <main className="min-h-screen bg-neutral-950 px-6 py-16 text-neutral-50">
      <section className="mx-auto flex max-w-3xl flex-col gap-6">
        <p className="text-sm uppercase text-emerald-300">__PROJECT_NAME__</p>
        <h1 className="text-4xl font-semibold tracking-normal sm:text-5xl">
          {message}
        </h1>
      </section>
    </main>
  );
}
