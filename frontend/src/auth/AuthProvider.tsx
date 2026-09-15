import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { labelGuardianApiV1 } from "../api/labelGuardianApi";
import type { Role, User } from "../domain/types";
import { getDemoAuthCredentials, isDemoAuthEmail } from "./demoAuth";
import {
  authConfigurationError,
  isSupabaseAuthEnabled,
  supabase,
} from "./supabase";

interface AuthContextValue {
  enabled: boolean;
  loading: boolean;
  user: User | null;
  isDemoSession: boolean;
  error: string;
  signIn: (email: string, password: string) => Promise<void>;
  signInDemo: (role: Role) => Promise<void>;
  signUp: (name: string, email: string, password: string) => Promise<string>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const initialsFor = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const enabled = isSupabaseAuthEnabled();
  const [loading, setLoading] = useState(enabled);
  const [user, setUser] = useState<User | null>(null);
  const [isDemoSession, setIsDemoSession] = useState(false);
  const [error, setError] = useState(authConfigurationError);

  const loadProfile = useCallback(
    async (
      accessToken: string,
      options: { demoSession?: boolean; expectedRole?: Role } = {},
    ) => {
      const profile = await labelGuardianApiV1.getMyProfile(accessToken);
      if (options.expectedRole && profile.role !== options.expectedRole) {
        throw new Error(
          `The Supabase demo account is configured as ${profile.role}, not ${options.expectedRole}.`,
        );
      }
      const mapped: User = {
        id: profile.id,
        email: profile.email,
        name: profile.displayName,
        role: profile.role,
        avatarInitials: initialsFor(profile.displayName),
      };
      const demoSession = options.demoSession ?? false;
      setIsDemoSession(demoSession);
      setUser(mapped);
      setError("");
      return mapped;
    },
    [],
  );

  useEffect(() => {
    if (!enabled || !supabase) {
      setLoading(false);
      return;
    }
    let active = true;
    void supabase.auth.getSession().then(async ({ data, error: sessionError }) => {
      if (!active) return;
      try {
        if (sessionError) throw sessionError;
        if (data.session) {
          await loadProfile(data.session.access_token, {
            demoSession: isDemoAuthEmail(data.session.user.email),
          });
        }
      } catch (nextError) {
        if (active) {
          setUser(null);
          setError(nextError instanceof Error ? nextError.message : "Không thể tải hồ sơ người dùng.");
        }
      } finally {
        if (active) setLoading(false);
      }
    });
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!active) return;
      if (!session) {
        queryClient.clear();
        setIsDemoSession(false);
        setUser(null);
        setLoading(false);
        return;
      }
      // Supabase advises deferring follow-up client work from this callback.
      window.setTimeout(() => {
        if (!active) return;
        void loadProfile(session.access_token, {
          demoSession: isDemoAuthEmail(session.user.email),
        }).catch((nextError: unknown) => {
          setUser(null);
          setError(nextError instanceof Error ? nextError.message : "Không thể tải hồ sơ người dùng.");
        });
      }, 0);
    });
    return () => {
      active = false;
      subscription.subscription.unsubscribe();
    };
  }, [enabled, loadProfile, queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      enabled,
      loading,
      user,
      isDemoSession,
      error,
      signIn: async (email, password) => {
        if (!supabase) throw new Error(authConfigurationError || "Supabase Auth chưa được cấu hình.");
        setLoading(true);
        setError("");
        setIsDemoSession(false);
        try {
          const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password });
          if (signInError) throw signInError;
          if (!data.session) throw new Error("Supabase không trả về phiên đăng nhập.");
          await loadProfile(data.session.access_token, {
            demoSession: isDemoAuthEmail(data.session.user.email),
          });
        } finally {
          setLoading(false);
        }
      },
      signInDemo: async (role) => {
        if (!supabase) {
          throw new Error(
            authConfigurationError || "Supabase Auth chưa được cấu hình.",
          );
        }
        const credentials = getDemoAuthCredentials(role);
        setLoading(true);
        setError("");
        queryClient.clear();
        setIsDemoSession(true);
        setUser(null);
        try {
          const { data, error: signInError } =
            await supabase.auth.signInWithPassword(credentials);
          if (signInError) throw signInError;
          if (!data.session) {
            throw new Error("Supabase không trả về phiên demo.");
          }
          await loadProfile(data.session.access_token, {
            demoSession: true,
            expectedRole: role,
          });
        } catch (nextError) {
          setIsDemoSession(false);
          setUser(null);
          const { data } = await supabase.auth.getSession();
          if (data.session) {
            await supabase.auth.signOut({ scope: "local" });
          }
          throw nextError;
        } finally {
          setLoading(false);
        }
      },
      signUp: async (name, email, password) => {
        if (!supabase) throw new Error(authConfigurationError || "Supabase Auth chưa được cấu hình.");
        setLoading(true);
        setError("");
        try {
          const { data, error: signUpError } = await supabase.auth.signUp({
            email,
            password,
            options: { data: { full_name: name } },
          });
          if (signUpError) throw signUpError;
          if (data.session) {
            await loadProfile(data.session.access_token);
            return "Tài khoản đã được tạo và đăng nhập.";
          }
          return "Tài khoản đã được tạo. Hãy xác nhận email trước khi đăng nhập.";
        } finally {
          setLoading(false);
        }
      },
      signOut: async () => {
        if (supabase) await supabase.auth.signOut();
        queryClient.clear();
        setIsDemoSession(false);
        setUser(null);
      },
    }),
    [enabled, error, isDemoSession, loadProfile, loading, queryClient, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
