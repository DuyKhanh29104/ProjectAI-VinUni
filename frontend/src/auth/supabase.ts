import { createClient, type SupabaseClient } from "@supabase/supabase-js";

type RuntimeImportMeta = ImportMeta & {
  env?: Record<string, string | undefined>;
};

const environment = (import.meta as RuntimeImportMeta).env;
// A missing production build variable must never create a mock admin session.
// Local mock mode remains available through the explicit .env.example value.
const authMode = (environment?.VITE_AUTH_MODE ?? "supabase").toLowerCase();
const supabaseUrl = environment?.VITE_SUPABASE_URL?.trim() ?? "";
const supabaseAnonKey = environment?.VITE_SUPABASE_ANON_KEY?.trim() ?? "";

export const isSupabaseAuthEnabled = () => authMode === "supabase";

export const authConfigurationError = isSupabaseAuthEnabled()
  ? !supabaseUrl
    ? "VITE_SUPABASE_URL is required when VITE_AUTH_MODE=supabase."
    : !supabaseAnonKey
      ? "VITE_SUPABASE_ANON_KEY is required when VITE_AUTH_MODE=supabase."
      : ""
  : "";

export const supabase: SupabaseClient | null = authConfigurationError
  ? null
  : isSupabaseAuthEnabled()
    ? createClient(supabaseUrl, supabaseAnonKey, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
        },
      })
    : null;

export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data, error } = await supabase.auth.getSession();
  if (error) return null;
  return data.session?.access_token ?? null;
}
