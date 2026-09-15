import { useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { appRoutes } from "./config/informationArchitecture";
import { cloudDatasets } from "./config/cloudDataset";
import {
  pathForDatasetView,
  pathForView,
  viewFromPath,
} from "./config/routing";
import type { Role, User } from "./domain/types";
import type { DemoMode } from "./domain/types";
import {
  AppShell,
  MockLoginScreen,
  type PrimaryViewId,
} from "./components/layout";
import { AuthenticatedLoginScreen } from "./components/AuthenticatedLoginScreen";
import { useAuth } from "./auth/AuthProvider";
import { DemoStateBoundary } from "./components/DemoState";
import { OverviewView } from "./views/OverviewView";
import { QAQueueView } from "./features/qa-queue/QAQueueView";
import { QACasesView } from "./features/qa-queue/QACasesView";
import { CaseDetailView } from "./views/CaseDetailView";
import { AnnotatorWorkspaceView } from "./views/AnnotatorWorkspaceView";
import { ReportsView } from "./views/ReportsView";
import { DatasetRunView } from "./views/DatasetRunView";
import { PipelineView } from "./views/PipelineView";
import { SettingsView } from "./views/SettingsView";
import { TutorialView } from "./views/TutorialView";
import { LandingPage } from "./views/LandingPage";
import { useMockData } from "./state/MockDataProvider";
import { useTutorialProgress } from "./state/useTutorialProgress";
import { isApiDataSourceEnabled } from "./api/labelGuardianApi";
import { TutorialWelcomeDialog } from "./components/TutorialWelcomeDialog";
import "./styles/index.css";

function CaseDetailRoute({
  onBack,
  onEditLabels,
}: {
  onBack: () => void;
  onEditLabels: () => void;
}) {
  const { findingId } = useParams<{ findingId: string }>();
  return findingId ? (
    <CaseDetailView
      findingId={findingId}
      onBack={onBack}
      onEditLabels={onEditLabels}
    />
  ) : (
    <Navigate to="/qa-queue" replace />
  );
}

function App() {
  const { state, actions } = useMockData();
  const auth = useAuth();
  const apiDataSourceEnabled = isApiDataSourceEnabled();
  const location = useLocation();
  const routerNavigate = useNavigate();
  const activeView = viewFromPath(location.pathname);
  const [mockSignedIn, setMockSignedIn] = useState(false);
  const [signedInUser, setSignedInUser] = useState<User | null>(null);
  const [localUsers, setLocalUsers] = useState<User[]>([]);
  const [demoMode, setDemoMode] = useState<DemoMode>("ready");
  const [language, setLanguage] = useState<"en" | "vi">(() => {
    return (localStorage.getItem("label-guardian-lang") as "en" | "vi") || "en";
  });
  const changeLanguage = (lang: "en" | "vi") => {
    setLanguage(lang);
    localStorage.setItem("label-guardian-lang", lang);
  };
  const searchParams = new URLSearchParams(location.search);
  const cloudDatasetId = searchParams.get("dataset") || cloudDatasets[0].id;
  const authUsers = [...state.users, ...localUsers];
  const activeUser = auth.enabled
    ? auth.user
    : (signedInUser ??
      (apiDataSourceEnabled
        ? {
            id: "api-default-user",
            email: "reviewer@labelguardian.space",
            name: "QA Specialist",
            role: "reviewer",
            avatarInitials: "QA",
          }
        : (state.users.find((user) => user.id === state.activeUserId) ??
          state.users[0])));
  const mockSelectedDataset =
    state.datasets.find((dataset) => dataset.id === state.selectedDatasetId) ??
    state.datasets[0];
  const selectedDataset = apiDataSourceEnabled
    ? (cloudDatasets.find((dataset) => dataset.id === cloudDatasetId) ??
      cloudDatasets[0])
    : mockSelectedDataset;
  const datasets = apiDataSourceEnabled ? cloudDatasets : state.datasets;
  const signedInForTutorial = auth.enabled ? Boolean(auth.user) : mockSignedIn;
  const tutorial = useTutorialProgress(
    signedInForTutorial && activeUser ? activeUser : null,
  );

  if (location.pathname === "/") {
    return <LandingPage lang={language} onChangeLang={changeLanguage} />;
  }

  const navigateToView = (view: PrimaryViewId) => {
    const path = pathForView(view);
    if (!apiDataSourceEnabled) {
      routerNavigate(path);
      return;
    }
    routerNavigate(pathForDatasetView(view, cloudDatasetId));
  };

  const navigateToCase = (findingId: string) => {
    routerNavigate(`/cases/${encodeURIComponent(findingId)}`);
  };

  const navigateToEditor = (split?: string, imageId?: string) => {
    const parameters = new URLSearchParams();
    if (split) parameters.set("split", split);
    if (imageId) parameters.set("imageId", imageId);
    routerNavigate(`/editor${parameters.size ? `?${parameters}` : ""}`);
  };

  const navigateToQaCases = (split: string, imageId: string) => {
    const parameters = new URLSearchParams({
      dataset: cloudDatasetId,
      split,
      imageId,
    });
    routerNavigate(`/qa-cases?${parameters}`);
  };

  const handleRoleChange = (role: Role) => {
    actions.setRole(role);
    const route = appRoutes.find((item) => item.id === activeView);
    if (route && !route.allowedRoles.includes(role)) {
      navigateToView("overview");
    }
  };

  const handleSignIn = (role: Role, email?: string) => {
    actions.setRole(role);
    const matchingUser = authUsers.find(
      (user) =>
        user.role === role &&
        (!email || user.email.toLowerCase() === email.toLowerCase()),
    );
    setSignedInUser(matchingUser ?? null);
    setMockSignedIn(true);
    navigateToView("overview");
  };

  const handleDemoSignIn = async (role: Role) => {
    await auth.signInDemo(role);
    actions.setRole(role);
    routerNavigate(pathForDatasetView("overview", cloudDatasetId), {
      replace: true,
    });
  };

  const handleRegister = (profile: Pick<User, "name" | "email" | "role">) => {
    const registeredUser: User = {
      ...profile,
      id: `local-user-${Date.now()}`,
      avatarInitials: profile.name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase() ?? "")
        .join(""),
    };
    setLocalUsers((users) => [
      ...users.filter((user) => user.email !== registeredUser.email),
      registeredUser,
    ]);
    actions.setRole(profile.role);
    setSignedInUser(registeredUser);
    setMockSignedIn(true);
    navigateToView("overview");
  };

  if (auth.enabled && !auth.user) {
    return (
      <AuthenticatedLoginScreen
        loading={auth.loading}
        configurationError={auth.error}
        demoUsers={authUsers}
        onDemoSignIn={handleDemoSignIn}
        onSignIn={async (email, password) => {
          await auth.signIn(email, password);
          routerNavigate(pathForDatasetView("overview", cloudDatasetId), {
            replace: true,
          });
        }}
        onRegister={async (name, email, password) => {
          const message = await auth.signUp(name, email, password);
          routerNavigate(pathForDatasetView("overview", cloudDatasetId), {
            replace: true,
          });
          return message;
        }}
      />
    );
  }

  if (!auth.enabled && !mockSignedIn) {
    return (
      <MockLoginScreen
        users={authUsers}
        onSignIn={handleSignIn}
        onRegister={handleRegister}
      />
    );
  }

  if (!activeUser || !selectedDataset) {
    return (
      <div className="fatal-state">Mock state chưa có user hoặc dataset.</div>
    );
  }

  const tutorialWelcome = tutorial.showWelcome ? (
    <TutorialWelcomeDialog
      role={activeUser.role}
      language={language}
      onStart={() => {
        tutorial.markWelcomeSeen();
        navigateToView("tutorial");
      }}
      onSkip={tutorial.markWelcomeSeen}
    />
  ) : null;

  const authorizedRoute = appRoutes.find((route) => route.id === activeView);
  if (
    auth.enabled &&
    authorizedRoute &&
    !authorizedRoute.allowedRoles.includes(activeUser.role)
  ) {
    return <Navigate to="/" replace />;
  }

  if (activeView === "annotator-workspace") {
    return (
      <>
        <AnnotatorWorkspaceView
          actorId={activeUser.id}
          onExit={() =>
            navigateToView(
              activeUser.role === "annotator" ? "qa-cases" : "qa-queue",
            )
          }
          onOpenQaCases={navigateToQaCases}
        />
        {tutorialWelcome}
      </>
    );
  }

  return (
    <>
      <AppShell
        activeView={activeView}
        activeRole={activeUser.role}
        activeUser={activeUser}
        selectedDataset={selectedDataset}
        qaRun={state.qaRun}
        datasets={datasets}
        routes={appRoutes}
        onNavigate={navigateToView}
        lang={language}
        onChangeLang={changeLanguage}
        onRoleChange={(role) => {
          if (auth.enabled) return;
          setSignedInUser((user) => (user ? { ...user, role } : user));
          handleRoleChange(role);
        }}
        onDatasetChange={(datasetId) => {
          if (!apiDataSourceEnabled) {
            actions.setDataset(datasetId);
            return;
          }
          const next = new URLSearchParams(location.search);
          next.set("dataset", datasetId);
          routerNavigate(`${location.pathname}?${next.toString()}`, {
            replace: true,
          });
        }}
        allowRoleSwitch={!auth.enabled}
        onSignOut={() => {
          if (auth.enabled) {
            void auth.signOut();
          } else {
            setSignedInUser(null);
            setMockSignedIn(false);
          }
        }}
        onReset={actions.reset}
      >
        <DemoStateBoundary
          mode={demoMode}
          viewLabel={
            appRoutes.find((route) => route.id === activeView)?.label ??
            "Workspace"
          }
          onReset={() => setDemoMode("ready")}
        >
          <Routes>
          <Route
            path="/overview"
            element={
              <OverviewView
                state={state}
                onOpenQueue={() => navigateToView("qa-queue")}
                onOpenFinding={navigateToCase}
              />
            }
          />
          <Route
            path="/qa-queue"
            element={
              <QAQueueView
                onOpenFinding={navigateToCase}
                onOpenEditor={navigateToEditor}
              />
            }
          />
          <Route
            path="/qa-cases"
            element={
              <QACasesView
                onOpenFinding={navigateToCase}
                onOpenEditor={navigateToEditor}
              />
            }
          />
          <Route
            path="/real-data"
            element={
              <Navigate to="/qa-queue?source=dataset&split=val" replace />
            }
          />
          <Route
            path="/cases/:findingId"
            element={
              apiDataSourceEnabled ? (
                <Navigate to="/qa-cases" replace />
              ) : (
                <CaseDetailRoute
                  onBack={() => navigateToView("qa-queue")}
                  onEditLabels={() => navigateToEditor()}
                />
              )
            }
          />
          <Route path="/reports" element={<ReportsView state={state} />} />
          <Route path="/dataset-runs" element={<DatasetRunView />} />
          <Route path="/pipeline" element={<PipelineView />} />
          <Route path="/settings" element={<SettingsView />} />
          <Route
            path="/tutorial"
            element={
              <TutorialView
                role={activeUser.role}
                language={language}
                completedStepIds={tutorial.completedStepIds}
                completedAt={tutorial.completedAt}
                onToggleStep={tutorial.toggleStep}
                onComplete={tutorial.completeTutorial}
                onReset={tutorial.resetTutorial}
                onNavigate={navigateToView}
              />
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </DemoStateBoundary>
      </AppShell>
      {tutorialWelcome}
    </>
  );
}

export default App;
