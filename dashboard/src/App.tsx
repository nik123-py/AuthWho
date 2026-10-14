import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { LiveDemoPage } from "./pages/LiveDemoPage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { SessionPage } from "./pages/SessionPage";
import { SessionsPage } from "./pages/SessionsPage";
import { SignInPage } from "./pages/SignInPage";

function Private({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  return token ? <>{children}</> : <SignInPage />;
}

function AppRoutes() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Private><SessionsPage /></Private>} />
        <Route path="/sessions/:sessionId" element={<Private><SessionPage /></Private>} />
        <Route path="/live" element={<Private><LiveDemoPage /></Private>} />
        <Route path="/policies" element={<Private><PoliciesPage /></Private>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

export function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
