import { BrowserRouter, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import { ScrollToTop } from "./hooks/useScrollMemory";
import Home from "./pages/Home";
import Detail from "./pages/Detail";
import Favorites from "./pages/Favorites";
import Tags from "./pages/Tags";
import TagPosts from "./pages/TagPosts";
import Uids from "./pages/Uids";
import UidPosts from "./pages/UidPosts";
import Timeline from "./pages/Timeline";
import AllTimeTop from "./pages/AllTimeTop";
import Blacklist from "./pages/Blacklist";
export default function App() {
  return (
    <BrowserRouter>
      <ScrollToTop />
      <Navbar />
      <main
        className="pt-[calc(60px+24px)] px-3 md:px-10 max-w-[1600px] ml-0 md:ml-[260px] transition-[margin] duration-300"
      >
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/post/:uid/:id" element={<Detail />} />
          <Route path="/favorites" element={<Favorites />} />
          <Route path="/tags" element={<Tags />} />
          <Route path="/tags/:tag" element={<TagPosts />} />
          <Route path="/uids" element={<Uids />} />
          <Route path="/uid/:uid" element={<UidPosts />} />
          <Route path="/timeline" element={<Timeline />} />
          <Route path="/timeline/:period" element={<Timeline />} />
          <Route path="/top" element={<AllTimeTop />} />
          <Route path="/blacklist" element={<Blacklist />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
