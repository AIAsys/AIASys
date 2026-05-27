import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, ArrowLeft, Shield } from "lucide-react";
import { useUserProfile } from "./hooks/useUserProfile";
import { UserProfileCard } from "./components/UserProfileCard";
import { AccountSecurityCard } from "./components/AccountSecurityCard";
import { LLMConfigCard } from "./components/LLMConfigCard";
import { SystemInfoCard } from "./components/SystemInfoCard";

export default function UserProfilePage() {
  const {
    isLoading,
    isSaving,
    isEditing,
    submitError,
    submitSuccess,
    isAuthenticated,
    authLoading,
    isLocalEditable,
    user,
    nameInput,
    phoneInput,
    setNameInput,
    setPhoneInput,
    startEdit,
    cancelEdit,
    saveProfile,
    showAuthModeNotice,
    reloadProfileContext,
  } = useUserProfile();

  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="w-full max-w-md">
          <CardContent className="pt-6 text-center">
            <p className="text-muted-foreground">当前用户上下文尚未就绪</p>
            <Button className="mt-4" onClick={reloadProfileContext}>
              重新加载
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="border-b border-border flex-shrink-0">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => window.history.back()}
            className="mr-4"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            返回
          </Button>
          <h1 className="text-lg font-semibold">个人资料</h1>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-20">
          <div className="space-y-6">
            {/* 认证提示 */}
            {isLocalEditable ? (
              <Alert className="bg-success-container border-success/20">
                <Shield className="h-4 w-4 text-success" />
                <AlertDescription className="text-success">
                  当前为本地认证模式，可直接在此页面修改昵称和手机号。
                </AlertDescription>
              </Alert>
            ) : (
              <Alert className="bg-info-container border-info/20">
                <Shield className="h-4 w-4 text-tertiary" />
                <AlertDescription className="text-tertiary">
                  当前运行模式不支持在线编辑个人资料。
                </AlertDescription>
              </Alert>
            )}

            {submitError && (
              <Alert variant="destructive">
                <AlertDescription>{submitError}</AlertDescription>
              </Alert>
            )}
            {submitSuccess && (
              <Alert className="bg-success-container border-success/20">
                <AlertDescription className="text-success">
                  {submitSuccess}
                </AlertDescription>
              </Alert>
            )}

            <UserProfileCard
              user={user}
              isEditing={isEditing}
              isSaving={isSaving}
              isLocalEditable={isLocalEditable}
              nameInput={nameInput}
              phoneInput={phoneInput}
              onNameChange={setNameInput}
              onPhoneChange={setPhoneInput}
              onStartEdit={startEdit}
              onCancelEdit={cancelEdit}
              onSave={saveProfile}
              onShowAuthModeNotice={showAuthModeNotice}
            />

            <AccountSecurityCard
              isLocalEditable={isLocalEditable}
              onShowAuthModeNotice={showAuthModeNotice}
            />

            <LLMConfigCard />

            <SystemInfoCard />
          </div>
        </div>
      </main>
    </div>
  );
}
