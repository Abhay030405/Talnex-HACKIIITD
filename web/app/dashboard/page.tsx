import { redirect } from "next/navigation";

import { auth } from "@/auth";
import { homePath } from "@/lib/types";

// An older address: each person goes to the workspace of their role.
export default async function Dashboard() {
  const role = (await auth())?.user?.role;
  redirect(role ? homePath(role) : "/login");
}
