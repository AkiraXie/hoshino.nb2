import { BrowserRouter, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Home from "./pages/Home";
import UidPosts from "./pages/UidPosts";
import Uids from "./pages/Uids";
import Detail from "./pages/Detail";
import Favorites from "./pages/Favorites";

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg-primary">
        <Navbar />
        <main className="max-w-[1600px] mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/uid/:uid" element={<UidPosts />} />
            <Route path="/uids" element={<Uids />} />
            <Route path="/post/:uid/:id" element={<Detail />} />
            <Route path="/favorites" element={<Favorites />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
