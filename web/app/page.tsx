import { Closing, Doors } from "@/components/landing/Doors";
import { Hero } from "@/components/landing/Hero";
import { Process } from "@/components/landing/Process";
import { Specimen } from "@/components/landing/Specimen";
import { redirectIfSignedIn } from "@/lib/session";

export default async function Home() {
  await redirectIfSignedIn();

  return (
    <>
      <Hero />
      <Process />
      <Specimen />
      <Doors />
      <Closing />
    </>
  );
}
