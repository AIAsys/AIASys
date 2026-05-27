import { useAuthContext } from "@/contexts/AuthContext";
import { CapabilitiesSection } from "./home-sections/CapabilitiesSection";
import { ScenariosSection } from "./home-sections/ScenariosSection";
import { SurfacesSection } from "./home-sections/SurfacesSection";
import { TrustSection } from "./home-sections/TrustSection";
import { WorkflowSection } from "./home-sections/WorkflowSection";

export const HomeSections = () => {
  const { isAuthenticated } = useAuthContext();

  return (
    <div className="relative">
      <SurfacesSection isAuthenticated={isAuthenticated} />
      <CapabilitiesSection />
      <ScenariosSection />
      <WorkflowSection />
      <TrustSection isAuthenticated={isAuthenticated} />
    </div>
  );
};
