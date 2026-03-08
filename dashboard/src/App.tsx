import { Routes, Route, NavLink } from "react-router-dom";
import Overview from "./pages/Overview.tsx";
import Projects from "./pages/Projects.tsx";
import Sessions from "./pages/Sessions.tsx";
import Transcript from "./pages/Transcript.tsx";
import Tokens from "./pages/Tokens.tsx";
import StudyConfig from "./pages/StudyConfig.tsx";
import Scripts from "./pages/Scripts.tsx";
import Settings from "./pages/Settings.tsx";
import Organizations from "./pages/Organizations.tsx";
import OrganizationDetail from "./pages/OrganizationDetail.tsx";
import OrganizationSettings from "./pages/OrganizationSettings.tsx";
import JobNotifications from "./components/JobNotifications.tsx";

function App() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>Open Uplift</h1>
        <nav>
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/projects">Projects</NavLink>
          <NavLink to="/sessions">Sessions</NavLink>
          <NavLink to="/organizations">Organizations</NavLink>
          <NavLink to="/scripts">Judge</NavLink>
          <NavLink to="/study-config">Survey</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/organizations" element={<Organizations />} />
          <Route path="/organizations/:orgId" element={<OrganizationDetail />} />
          <Route path="/organizations/:orgId/settings" element={<OrganizationSettings />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/sessions/:sessionId/transcript" element={<Transcript />} />
          <Route path="/tokens" element={<Tokens />} />
          <Route path="/study-config" element={<StudyConfig />} />
          <Route path="/scripts" element={<Scripts />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
      <JobNotifications />
    </div>
  );
}

export default App;
