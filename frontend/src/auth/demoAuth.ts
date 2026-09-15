import type { Role } from "../domain/types";

type RuntimeImportMeta = ImportMeta & {
  env?: Record<string, string | undefined>;
};

export interface DemoAuthCredentials {
  email: string;
  password: string;
}

const environment = (import.meta as RuntimeImportMeta).env;

const demoCredentialsByRole: Record<Role, DemoAuthCredentials> = {
  annotator: {
    email:
      environment?.VITE_SUPABASE_DEMO_ANNOTATOR_EMAIL?.trim().toLowerCase() ??
      "",
    password:
      environment?.VITE_SUPABASE_DEMO_ANNOTATOR_PASSWORD?.trim() ?? "",
  },
  reviewer: {
    email:
      environment?.VITE_SUPABASE_DEMO_REVIEWER_EMAIL?.trim().toLowerCase() ??
      "",
    password:
      environment?.VITE_SUPABASE_DEMO_REVIEWER_PASSWORD?.trim() ?? "",
  },
  admin: {
    email:
      environment?.VITE_SUPABASE_DEMO_ADMIN_EMAIL?.trim().toLowerCase() ?? "",
    password: environment?.VITE_SUPABASE_DEMO_ADMIN_PASSWORD?.trim() ?? "",
  },
};

export function getDemoAuthCredentials(role: Role): DemoAuthCredentials {
  const credentials = demoCredentialsByRole[role];
  if (!credentials.email || !credentials.password) {
    throw new Error(
      `Supabase quick login for ${role} is not configured. Set its VITE_SUPABASE_DEMO_*_EMAIL and VITE_SUPABASE_DEMO_*_PASSWORD variables.`,
    );
  }
  return credentials;
}

export function isDemoAuthEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const normalizedEmail = email.trim().toLowerCase();
  return Object.values(demoCredentialsByRole).some(
    (credentials) =>
      Boolean(credentials.email) && credentials.email === normalizedEmail,
  );
}
