import { useState, type ReactNode } from "react";
import { Brain, GraduationCap, Menu, X } from "lucide-react";
import "../styles/AppShell.css";

export type NavigationItem = {
    label: string;
    icon: ReactNode;
    onClick: () => void;
    active: boolean;
};

type AppShellProps = {
    userName: string;
    navItems: NavigationItem[];
    onLogout: () => void;
    children: ReactNode;
};

export default function AppShell({ userName, navItems, onLogout, children }: AppShellProps) {
    const [drawerOpen, setDrawerOpen] = useState(false);

    function selectItem(item: NavigationItem) {
        item.onClick();
        setDrawerOpen(false);
    }

    return (
        <div className="app-shell">
            <header className="app-topbar">
                <div className="app-header-left">
                    <button
                        type="button"
                        className="app-menu-button"
                        aria-label={drawerOpen ? "Close navigation menu" : "Open navigation menu"}
                        aria-expanded={drawerOpen}
                        aria-controls="app-main-navigation"
                        onClick={() => setDrawerOpen((open) => !open)}
                    >
                        {drawerOpen ? <X size={22} /> : <Menu size={22} />}
                    </button>
                    <button
                        type="button"
                        className="app-brand"
                        onClick={() => {
                            navItems.find((item) => item.label === "Dashboard")?.onClick();
                            setDrawerOpen(false);
                        }}
                    >
                        <span className="app-brand-icon"><Brain size={24} /></span>
                        <span className="app-brand-copy">
                            <strong>AdaptiveLearning</strong>
                            <small>Learn at your own pace</small>
                        </span>
                    </button>
                </div>
                <div className="app-workspace">
                    <GraduationCap size={18} />
                    <span className="app-user-name">{userName}</span>
                    <button type="button" className="app-logout-button" onClick={onLogout}>Log out</button>
                </div>
            </header>

            {drawerOpen && (
                <button
                    type="button"
                    className="app-drawer-backdrop"
                    aria-label="Close navigation menu"
                    onClick={() => setDrawerOpen(false)}
                />
            )}

            <aside
                id="app-main-navigation"
                className={`app-sidebar ${drawerOpen ? "is-open" : ""}`}
                aria-label="Main navigation"
            >
                <div className="app-sidebar-label">WORKSPACE</div>
                <nav className="app-nav-list">
                    {navItems.map((item) => (
                        <button
                            key={item.label}
                            type="button"
                            onClick={() => selectItem(item)}
                            aria-current={item.active ? "page" : undefined}
                            className={`app-nav-item ${item.active ? "is-active" : ""}`}
                        >
                            {item.icon}<span>{item.label}</span>
                        </button>
                    ))}
                </nav>
                <div className="app-sidebar-foot">Learn at your own pace</div>
            </aside>

            <div className="app-content">{children}</div>
        </div>
    );
}
