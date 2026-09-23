import { useEffect } from "react";
import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import { StatusBanner } from "../shared/components/StatusBanner";
import { IdleWarningModal } from "@/shared/components/IdleWarningModal";
import { ScaleToFit } from "@/shared/components/ScaleToFit";
import { RequireAuth } from "@/shared/auth/RequireAuth";
import { useAuthStore } from "@/shared/auth/store";
import { applyTheme, useThemeStore } from "@/shared/theme/store";
import { MainPage } from "@/pages/MainPage";
import { SignInPage } from "@/pages/SignInPage";
import { SignUpPage } from "@/pages/SignUpPage";
import { InvitePage } from "@/pages/InvitePage";
import { ForgotPasswordPage } from "@/pages/ForgotPasswordPage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";
import { AdminPage } from "@/pages/AdminPage";
import { ViewEditorPage } from "@/pages/ViewEditorPage";
import { DataSourcesPage } from "@/pages/DataSourcesPage";
import { ActionsPage } from "@/pages/ActionsPage";
import { BotPage } from "@/pages/BotPage";
import { LandingPage } from "@/pages/LandingPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SecurityPage } from "@/pages/SecurityPage";
import { DatabasePage } from "@/pages/DatabasePage";
import { DeployPage } from "@/pages/DeployPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { IntelligencePage } from "@/pages/IntelligencePage";
import { DataSchemaPage } from "@/pages/DataSchemaPage";
import { TemplatesPage } from "@/pages/TemplatesPage";
import { LearningPage } from "@/pages/LearningPage";
import { RulesPage } from "@/pages/RulesPage";
import { ModulesPage } from "@/pages/ModulesPage";
import { EmailTemplatesPage } from "@/pages/EmailTemplatesPage";
import { ThemesPage } from "@/pages/ThemesPage";
import { AccountPage } from "@/pages/AccountPage";
import { EditorPage } from "@/pages/EditorPage";
import { PreviewPage } from "@/pages/PreviewPage";
import { DbHistoryPage } from "@/pages/DbHistoryPage";
import { DataPage } from "@/pages/DataPage";
import { OAuthCallbackPage } from "@/pages/OAuthCallbackPage";
import { KnowledgeBasePage } from "@/pages/KnowledgeBasePage";
import { DocumentRegistrarPage } from "@/pages/DocumentRegistrarPage";

export function EditorApp() {
  const bootstrap = useAuthStore((s) => s.bootstrap);
  const theme = useThemeStore((s) => s.theme);

  // Resolve "am I already logged in?" once on app start.
  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  // Reflect the persisted theme onto <html> on first paint.
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return (
    <BrowserRouter basename="/editor">
      <StatusBanner />
      <IdleWarningModal />
      <Routes>
        {/* Public */}
        <Route path="/landing" element={<LandingPage />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/signup" element={<SignUpPage />} />
        <Route path="/invite/:token" element={<InvitePage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/auth/yandex/callback" element={<OAuthCallbackPage />} />
        <Route path="/auth/vk/callback" element={<OAuthCallbackPage />} />

        {/* Private */}
        <Route path="/"        element={<RequireAuth><ScaleToFit><MainPage /></ScaleToFit></RequireAuth>} />
        <Route path="/admin"   element={<RequireAuth><ScaleToFit><AdminPage /></ScaleToFit></RequireAuth>} />
        <Route path="/views"   element={<RequireAuth><ScaleToFit><ViewEditorPage /></ScaleToFit></RequireAuth>} />
        <Route path="/data"    element={<RequireAuth><ScaleToFit><DataSourcesPage /></ScaleToFit></RequireAuth>} />
        <Route path="/actions" element={<RequireAuth><ScaleToFit><ActionsPage /></ScaleToFit></RequireAuth>} />
        <Route path="/bot"      element={<RequireAuth><ScaleToFit><BotPage /></ScaleToFit></RequireAuth>} />
        <Route path="/settings" element={<RequireAuth><ScaleToFit><SettingsPage /></ScaleToFit></RequireAuth>} />
        <Route path="/security" element={<RequireAuth><ScaleToFit><SecurityPage /></ScaleToFit></RequireAuth>} />
        <Route path="/database" element={<RequireAuth><ScaleToFit><DatabasePage /></ScaleToFit></RequireAuth>} />
        <Route path="/deploy"   element={<RequireAuth><ScaleToFit><DeployPage /></ScaleToFit></RequireAuth>} />
        <Route path="/profile"  element={<RequireAuth><ScaleToFit><ProfilePage /></ScaleToFit></RequireAuth>} />
        <Route path="/intel"    element={<RequireAuth><ScaleToFit><IntelligencePage /></ScaleToFit></RequireAuth>} />
        <Route path="/schema"    element={<RequireAuth><ScaleToFit><DataSchemaPage /></ScaleToFit></RequireAuth>} />
        <Route path="/templates" element={<RequireAuth><ScaleToFit><TemplatesPage /></ScaleToFit></RequireAuth>} />
        <Route path="/learning"  element={<RequireAuth><ScaleToFit><LearningPage /></ScaleToFit></RequireAuth>} />
        <Route path="/rules"     element={<RequireAuth><ScaleToFit><RulesPage /></ScaleToFit></RequireAuth>} />
        <Route path="/modules"   element={<RequireAuth><ScaleToFit><ModulesPage /></ScaleToFit></RequireAuth>} />
        <Route path="/themes"    element={<RequireAuth><ScaleToFit><ThemesPage /></ScaleToFit></RequireAuth>} />
        <Route path="/account"    element={<RequireAuth><ScaleToFit><AccountPage /></ScaleToFit></RequireAuth>} />
        <Route path="/editor"     element={<RequireAuth><ScaleToFit><EditorPage /></ScaleToFit></RequireAuth>} />
        <Route path="/preview"    element={<RequireAuth><ScaleToFit><PreviewPage /></ScaleToFit></RequireAuth>} />
        <Route path="/db-history" element={<RequireAuth><ScaleToFit><DbHistoryPage /></ScaleToFit></RequireAuth>} />
        <Route path="/data-page"  element={<RequireAuth><ScaleToFit><DataPage /></ScaleToFit></RequireAuth>} />
        <Route path="/knowledge-base" element={<RequireAuth><ScaleToFit><KnowledgeBasePage /></ScaleToFit></RequireAuth>} />
        <Route path="/documents" element={<RequireAuth><ScaleToFit><DocumentRegistrarPage /></ScaleToFit></RequireAuth>} />
        <Route path="/notifications" element={<RequireAuth><ScaleToFit><EmailTemplatesPage /></ScaleToFit></RequireAuth>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
