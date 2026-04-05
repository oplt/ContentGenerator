import { useMemo, useState, type ReactNode } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
    AppBar,
    Avatar,
    Badge,
    Box,
    Button,
    Chip,
    Divider,
    Drawer,
    IconButton,
    List,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Stack,
    Toolbar,
    Tooltip,
    Typography,
    useMediaQuery,
} from "@mui/material";
import {
    AdminPanelSettings as AdminIcon,
    CalendarMonth as CalendarIcon,
    ChevronLeft as ChevronLeftIcon,
    ChevronRight as ChevronRightIcon,
    Dashboard as DashboardIcon,
    DarkMode as DarkModeIcon,
    Extension as PlatformIcon,
    FolderOpen as ProjectsIcon,
    LightMode as LightModeIcon,
    Logout as LogoutIcon,
    Menu as MenuIcon,
    Notifications as NotificationsIcon,
    Person as ProfileIcon,
    Settings as SettingsIcon,
    SettingsBrightness as SystemModeIcon,
} from "@mui/icons-material";
import { alpha, useTheme } from "@mui/material/styles";
import { useQuery } from "@tanstack/react-query";
import { useColorMode } from "../../app/colorModeContext";
import { getNotifications } from "../../api/notifications";
import { getProfile } from "../../api/profile";
import { getMe } from "../../api/users";
import { useAuth } from "../../hooks/useAuth";
import { usePlatformMetadata } from "../../hooks/usePlatformMetadata";
import { getInitials } from "../../utils/formatters";

const DRAWER_WIDTH = 288;
const COLLAPSED_DRAWER_WIDTH = 96;

type NavItem = {
    label: string;
    icon: ReactNode;
    path: string;
    adminOnly?: boolean;
    badge?: number;
    group: "workspace" | "admin";
};

function ThemeToggle() {
    const { colorMode, setColorMode } = useColorMode();
    const cycle = () => {
        const next: Record<string, typeof colorMode> = { light: "dark", dark: "system", system: "light" };
        setColorMode(next[colorMode]);
    };
    const icon =
        colorMode === "light" ? <LightModeIcon fontSize="small" /> :
        colorMode === "dark" ? <DarkModeIcon fontSize="small" /> :
        <SystemModeIcon fontSize="small" />;

    return (
        <Tooltip title={`Theme: ${colorMode}`}>
            <IconButton onClick={cycle} size="small" sx={{ border: 1, borderColor: "divider", bgcolor: "background.paper" }}>
                {icon}
            </IconButton>
        </Tooltip>
    );
}

function NavBlock({
    title,
    items,
    currentPath,
    onNavigate,
    collapsed,
}: {
    title: string;
    items: NavItem[];
    currentPath: string;
    onNavigate: (path: string) => void;
    collapsed: boolean;
}) {
    if (items.length === 0) {
        return null;
    }

    return (
        <Stack spacing={1}>
            {!collapsed && (
                <Typography variant="overline" color="text.secondary" sx={{ px: 1.5 }}>
                    {title}
                </Typography>
            )}
            <List disablePadding sx={{ display: "grid", gap: 0.75 }}>
                {items.map((item) => {
                    const selected =
                        item.path === "/dashboard"
                            ? currentPath === item.path
                            : currentPath.startsWith(item.path);
                    const itemButton = (
                        <ListItemButton
                            key={item.path}
                            selected={selected}
                            onClick={() => onNavigate(item.path)}
                            sx={
                                collapsed
                                    ? {
                                          minHeight: 48,
                                          px: 1,
                                          justifyContent: "center",
                                      }
                                    : undefined
                            }
                        >
                            <ListItemIcon
                                sx={{
                                    minWidth: collapsed ? "auto" : 40,
                                    justifyContent: "center",
                                }}
                            >
                                {item.badge ? (
                                    <Badge badgeContent={item.badge} color="error">
                                        {item.icon}
                                    </Badge>
                                ) : (
                                    item.icon
                                )}
                            </ListItemIcon>
                            {!collapsed && (
                                <ListItemText
                                    primary={item.label}
                                    secondary={selected ? "Current section" : undefined}
                                    secondaryTypographyProps={{ sx: { fontSize: "0.74rem" } }}
                                />
                            )}
                        </ListItemButton>
                    );

                    if (!collapsed) {
                        return itemButton;
                    }

                    return (
                        <Tooltip key={item.path} title={item.label} placement="right">
                            {itemButton}
                        </Tooltip>
                    );
                })}
            </List>
        </Stack>
    );
}

export function AppLayout() {
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [desktopNavCollapsed, setDesktopNavCollapsed] = useState(false);
    const { logout, isAdmin } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down("md"));
    const { data: platformMetadata } = usePlatformMetadata();

    const { data: currentUser } = useQuery({
        queryKey: ["me"],
        queryFn: getMe,
    });
    const { data: notifications } = useQuery({
        queryKey: ["notifications"],
        queryFn: getNotifications,
        refetchInterval: 60_000,
    });
    const { data: profile } = useQuery({
        queryKey: ["profile"],
        queryFn: getProfile,
        staleTime: 5 * 60_000,
    });

    const unreadCount = notifications?.filter((notification) => !notification.is_read).length ?? 0;
    const appName = platformMetadata?.app_name ?? "Your App";
    const coreDomainPlural = platformMetadata?.core_domain_plural ?? "Projects";
    const hasUserPlatformModule =
        platformMetadata?.module_catalog.some((item) => item.user_visible && item.enabled) ?? false;
    const drawerCollapsed = !isMobile && desktopNavCollapsed;
    const desktopDrawerWidth = drawerCollapsed ? COLLAPSED_DRAWER_WIDTH : DRAWER_WIDTH;

    const navItems = useMemo<NavItem[]>(
        () => [
            { label: "Dashboard", icon: <DashboardIcon />, path: "/dashboard", group: "workspace" },
            { label: "Calendar", icon: <CalendarIcon />, path: "/calendar", group: "workspace" },
            { label: coreDomainPlural, icon: <ProjectsIcon />, path: "/projects", group: "workspace" },
            ...(hasUserPlatformModule
                ? [{ label: "Platform", icon: <PlatformIcon />, path: "/platform", group: "workspace" as const }]
                : []),
            {
                label: "Notifications",
                icon: <NotificationsIcon />,
                path: "/notifications",
                group: "workspace",
                badge: unreadCount || undefined,
            },
            { label: "Profile", icon: <ProfileIcon />, path: "/profile", group: "workspace" },
            { label: "Users", icon: <AdminIcon />, path: "/admin/users", adminOnly: true, group: "admin" },
            { label: "Platform Admin", icon: <PlatformIcon />, path: "/admin/platform", adminOnly: true, group: "admin" },
            { label: "Settings", icon: <SettingsIcon />, path: "/admin/settings", adminOnly: true, group: "admin" },
        ],
        [coreDomainPlural, hasUserPlatformModule, unreadCount]
    );

    const visibleNavItems = navItems.filter((item) => !item.adminOnly || isAdmin);
    const currentItem = visibleNavItems.find((item) =>
        item.path === "/dashboard" ? location.pathname === item.path : location.pathname.startsWith(item.path)
    );
    const avatarLabel = getInitials(currentUser?.full_name, currentUser?.email);

    function handleNavigate(path: string) {
        navigate(path);
        setDrawerOpen(false);
    }

    async function handleSignOut() {
        await logout();
        setDrawerOpen(false);
        navigate("/", { replace: true });
    }

    const drawerContent = (
        <Stack sx={{ height: "100%", p: drawerCollapsed ? 1.25 : 2 }}>
            <Tooltip
                title={appName}
                placement="right"
                disableHoverListener={!drawerCollapsed}
            >
                <Box
                    sx={(currentTheme) => ({
                        borderRadius: 4,
                        px: drawerCollapsed ? 1 : 2,
                        py: drawerCollapsed ? 1.75 : 2.25,
                        mb: 2,
                        border: `1px solid ${currentTheme.palette.divider}`,
                        background: `linear-gradient(155deg, ${alpha(currentTheme.palette.primary.main, currentTheme.palette.mode === "dark" ? 0.3 : 0.12)} 0%, ${alpha(
                            currentTheme.palette.secondary.main,
                            currentTheme.palette.mode === "dark" ? 0.18 : 0.08
                        )} 100%)`,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: drawerCollapsed ? "center" : "flex-start",
                        textAlign: drawerCollapsed ? "center" : "left",
                    })}
                >
                    {drawerCollapsed ? (
                        <Typography variant="h6" sx={{ lineHeight: 1 }}>
                            {appName.trim().charAt(0).toUpperCase() || "W"}
                        </Typography>
                    ) : (
                        <Box>
                            <Typography variant="overline" sx={{ color: "primary.main" }}>
                                Workspace
                            </Typography>
                            <Typography variant="h6" sx={{ mt: 0.5 }}>
                                {appName}
                            </Typography>
                            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                                A sharper control center for your team, customers, and operations.
                            </Typography>
                            {platformMetadata?.module_pack && (
                                <Chip
                                    label={`Pack: ${platformMetadata.module_pack}`}
                                    size="small"
                                    variant="outlined"
                                    sx={{ mt: 1.5 }}
                                />
                            )}
                        </Box>
                    )}
                </Box>
            </Tooltip>

            <Stack spacing={drawerCollapsed ? 1 : 2}>
                <NavBlock
                    title="Product"
                    items={visibleNavItems.filter((item) => item.group === "workspace")}
                    currentPath={location.pathname}
                    onNavigate={handleNavigate}
                    collapsed={drawerCollapsed}
                />
                {isAdmin && drawerCollapsed && <Divider sx={{ mx: 1.5 }} />}
                {isAdmin && (
                    <NavBlock
                        title="Administration"
                        items={visibleNavItems.filter((item) => item.group === "admin")}
                        currentPath={location.pathname}
                        onNavigate={handleNavigate}
                        collapsed={drawerCollapsed}
                    />
                )}
            </Stack>

            <Box sx={{ flexGrow: 1 }} />

            <Box
                sx={(currentTheme) => ({
                    p: drawerCollapsed ? 1.25 : 2,
                    borderRadius: 4,
                    border: `1px solid ${currentTheme.palette.divider}`,
                    backgroundColor: alpha(currentTheme.palette.background.paper, 0.78),
                })}
            >
                <Stack spacing={1.5} alignItems={drawerCollapsed ? "center" : "stretch"}>
                    <Stack
                        direction={drawerCollapsed ? "column" : "row"}
                        spacing={1.5}
                        alignItems="center"
                        justifyContent="center"
                        sx={{ width: "100%" }}
                    >
                        <Avatar
                            src={profile?.avatar_url ?? undefined}
                            sx={{ width: drawerCollapsed ? 40 : 44, height: drawerCollapsed ? 40 : 44 }}
                        >
                            {avatarLabel}
                        </Avatar>
                        {!drawerCollapsed && (
                            <Box sx={{ minWidth: 0 }}>
                                <Typography variant="subtitle2" noWrap>
                                    {currentUser?.full_name ?? "Your profile"}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" noWrap>
                                    {currentUser?.email ?? "Signed in"}
                                </Typography>
                            </Box>
                        )}
                    </Stack>
                    {drawerCollapsed ? (
                        <Stack spacing={1}>
                            <Tooltip title="Manage profile" placement="right">
                                <IconButton
                                    onClick={() => handleNavigate("/profile")}
                                    sx={{ border: 1, borderColor: "divider", bgcolor: "background.paper" }}
                                >
                                    <ProfileIcon fontSize="small" />
                                </IconButton>
                            </Tooltip>
                            <Tooltip title="Sign out" placement="right">
                                <IconButton
                                    onClick={() => void handleSignOut()}
                                    sx={{ border: 1, borderColor: "divider", bgcolor: "background.paper" }}
                                >
                                    <LogoutIcon fontSize="small" />
                                </IconButton>
                            </Tooltip>
                        </Stack>
                    ) : (
                        <Stack spacing={1}>
                            <Button variant="outlined" fullWidth onClick={() => handleNavigate("/profile")}>
                                Manage profile
                            </Button>
                            <Button
                                variant="text"
                                color="inherit"
                                fullWidth
                                startIcon={<LogoutIcon />}
                                onClick={() => void handleSignOut()}
                            >
                                Sign out
                            </Button>
                        </Stack>
                    )}
                </Stack>
            </Box>
        </Stack>
    );

    return (
        <Box sx={{ minHeight: "100vh" }}>
            <AppBar
                position="fixed"
                elevation={0}
                sx={{
                    left: { md: `${desktopDrawerWidth}px` },
                    width: { md: `calc(100% - ${desktopDrawerWidth}px)` },
                    borderBottom: 1,
                    borderColor: "divider",
                    backgroundColor: alpha(theme.palette.background.default, theme.palette.mode === "dark" ? 0.82 : 0.78),
                    color: "text.primary",
                    transition: theme.transitions.create(["left", "width"], {
                        duration: theme.transitions.duration.shorter,
                    }),
                }}
            >
                <Toolbar sx={{ minHeight: { xs: 72, md: 80 }, px: { xs: 2, md: 3 } }}>
                    {isMobile ? (
                        <IconButton edge="start" onClick={() => setDrawerOpen(true)} sx={{ mr: 1.25 }}>
                            <MenuIcon />
                        </IconButton>
                    ) : (
                        <Tooltip title={drawerCollapsed ? "Expand menu" : "Collapse menu"}>
                            <IconButton
                                edge="start"
                                onClick={() => setDesktopNavCollapsed((current) => !current)}
                                sx={{ mr: 1.25, border: 1, borderColor: "divider", bgcolor: "background.paper" }}
                            >
                                {drawerCollapsed ? <ChevronRightIcon /> : <ChevronLeftIcon />}
                            </IconButton>
                        </Tooltip>
                    )}
                    <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                        <Typography variant="caption" color="text.secondary">
                            {appName}
                        </Typography>
                        <Typography variant="h6" noWrap>
                            {currentItem?.label ?? "Workspace"}
                        </Typography>
                    </Box>
                    <ThemeToggle />
                </Toolbar>
            </AppBar>

            {isMobile ? (
                <Drawer
                    open={drawerOpen}
                    onClose={() => setDrawerOpen(false)}
                    ModalProps={{ keepMounted: true }}
                    sx={{ "& .MuiDrawer-paper": { width: DRAWER_WIDTH } }}
                >
                    {drawerContent}
                </Drawer>
            ) : (
                <Drawer
                    variant="permanent"
                    open
                    sx={{
                        width: desktopDrawerWidth,
                        flexShrink: 0,
                        "& .MuiDrawer-paper": {
                            width: desktopDrawerWidth,
                            boxSizing: "border-box",
                            overflowX: "hidden",
                            transition: theme.transitions.create("width", {
                                duration: theme.transitions.duration.shorter,
                            }),
                        },
                    }}
                >
                    {drawerContent}
                </Drawer>
            )}

            <Box
                component="main"
                sx={{
                    minHeight: "100vh",
                    ml: { md: `${desktopDrawerWidth}px` },
                    pt: { xs: "72px", md: "80px" },
                    transition: theme.transitions.create("margin-left", {
                        duration: theme.transitions.duration.shorter,
                    }),
                }}
            >
                <Outlet />
            </Box>
        </Box>
    );
}
