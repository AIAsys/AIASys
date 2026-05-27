import { useEffect } from "react";
import { Header } from "./Header";
import { HomeSections } from "./HomeSections";
import { Hero } from "./Hero";
import { syncHomeHashScroll } from "./navigation";

/**
 * 首页面组件
 * 展示艾斯的对外首页，包含导航、产品首屏和能力说明
 */
export default function HomePage() {
  useEffect(() => {
    syncHomeHashScroll();
  }, []);

  return (
    <div className="h-screen overflow-x-hidden overflow-y-auto bg-[linear-gradient(180deg,#ffffff_0%,#f8fafc_42%,#f7f7f3_100%)] scroll-smooth">
      <Header />
      <main>
        <Hero />
        <HomeSections />
      </main>
    </div>
  );
}
