import type { ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { CaptureProvider, useCapture } from "./capture/CaptureProvider";
import { Layout } from "./components/Layout";
import { RequireConsent, RequireSignIn } from "./components/guards";
import { CollectPage } from "./pages/CollectPage";
import { ConsentPage } from "./pages/ConsentPage";
import { FormPage } from "./pages/FormPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PayeesPage } from "./pages/PayeesPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { WritePage } from "./pages/WritePage";
import { SessionProvider, useSession } from "./session/SessionProvider";

const consented = (page: ReactNode) => <RequireConsent>{page}</RequireConsent>;

function AppRoutes() {
  const { signOut } = useSession();
  const capture = useCapture();

  // Flush and stop capture while the AuthWho stream is still valid, then end the session.
  const onSignOut = async () => {
    await capture.stop();
    await signOut();
  };

  return (
    <Layout onSignOut={onSignOut}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/what-we-collect" element={<CollectPage />} />
        <Route
          path="/consent"
          element={
            <RequireSignIn>
              <ConsentPage />
            </RequireSignIn>
          }
        />
        <Route path="/" element={consented(<HomePage />)} />
        <Route path="/write" element={consented(<WritePage />)} />
        <Route path="/form" element={consented(<FormPage />)} />
        <Route path="/payees" element={consented(<PayeesPage />)} />
        <Route path="/reports" element={consented(<ReportsPage />)} />
        <Route path="/settings" element={consented(<SettingsPage />)} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  );
}

export function App() {
  return (
    <SessionProvider>
      <CaptureProvider>
        <AppRoutes />
      </CaptureProvider>
    </SessionProvider>
  );
}
