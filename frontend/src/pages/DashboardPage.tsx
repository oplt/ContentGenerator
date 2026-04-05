import { useQuery } from "@tanstack/react-query";
import {
    Box,
    Button,
    Chip,
    Skeleton,
    Stack,
    Typography,
} from "@mui/material";
import {
    ArrowForward as ArrowForwardIcon,
    FolderOpen as ProjectsIcon,
    Notifications as NotificationsIcon,
    Security as SecurityIcon,
    VerifiedUser as VerifiedUserIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import { useNavigate } from "react-router-dom";
import { listProjects } from "../api/projects";
import { getNotifications } from "../api/notifications";
import { getMe } from "../api/users";
import { DashboardCalendar } from "../components/dashboard/DashboardCalendar";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { EmptyState } from "../components/ui/EmptyState";
import { usePlatformMetadata } from "../hooks/usePlatformMetadata";
import { formatDateTime, getFirstName } from "../utils/formatters";

export default function DashboardPage() {
    const navigate = useNavigate();
    const { data: platformMetadata } = usePlatformMetadata();
    const { data: user, isLoading: userLoading } = useQuery({
        queryKey: ["me"],
        queryFn: getMe,
    });
    const { data: projects, isLoading: projectsLoading } = useQuery({
        queryKey: ["projects"],
        queryFn: listProjects,
    });
    const { data: notifications, isLoading: notificationsLoading } = useQuery({
        queryKey: ["notifications"],
        queryFn: getNotifications,
    });

    const coreDomainPlural = platformMetadata?.core_domain_plural ?? "Projects";
    const firstName = getFirstName(user?.full_name) || "there";
    const unreadCount = notifications?.filter((item) => !item.is_read).length ?? 0;
    const recentNotifications = notifications?.slice(0, 5) ?? [];
    const accountChecks = [
        {
            label: "Email verification",
            value: user?.is_verified ? "Verified" : "Action needed",
            color: user?.is_verified ? "success.main" : "warning.main",
            description: user?.is_verified
                ? "Your sign-in identity is confirmed."
                : "Verify your email to improve recovery and trust.",
        },
        {
            label: "Multi-factor authentication",
            value: user?.mfa_enabled ? "Enabled" : "Recommended",
            color: user?.mfa_enabled ? "success.main" : "warning.main",
            description: user?.mfa_enabled
                ? "An extra layer of account protection is active."
                : "Turn on MFA to reduce account risk.",
        },
    ];

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Operations overview"
                title={`Welcome back, ${firstName}`}
                description={`Track ${coreDomainPlural.toLowerCase()}, account readiness, and recent signals from a single workspace built for fast scanning.`}
                actions={
                    <>
                        <Button variant="contained" endIcon={<ArrowForwardIcon />} onClick={() => navigate("/projects")}>
                            Open {coreDomainPlural}
                        </Button>
                        <Button variant="outlined" onClick={() => navigate("/notifications")}>
                            View inbox
                        </Button>
                    </>
                }
                meta={
                    <>
                        <Chip
                            label={
                                platformMetadata?.module_pack
                                    ? `Pack: ${platformMetadata.module_pack}`
                                    : "Standard workspace"
                            }
                            variant="outlined"
                        />
                        <Chip
                            label={
                                userLoading
                                    ? "Checking security"
                                    : user?.is_verified && user?.mfa_enabled
                                        ? "Account secure"
                                        : "Security actions pending"
                            }
                            color={user?.is_verified && user?.mfa_enabled ? "success" : "warning"}
                            variant="outlined"
                        />
                    </>
                }
            />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                        xl: "repeat(4, minmax(0, 1fr))",
                    },
                }}
            >
                <StatCard
                    label={coreDomainPlural}
                    value={projects?.length ?? 0}
                    description={`Total ${coreDomainPlural.toLowerCase()} in your workspace`}
                    icon={<ProjectsIcon />}
                    loading={projectsLoading}
                />
                <StatCard
                    label="Unread notifications"
                    value={unreadCount}
                    description="New updates waiting for a response"
                    icon={<NotificationsIcon />}
                    loading={notificationsLoading}
                    color="warning"
                />
                <StatCard
                    label="Email status"
                    value={user?.is_verified ? "Verified" : "Pending"}
                    description="Identity confirmation for your account"
                    icon={<VerifiedUserIcon />}
                    loading={userLoading}
                    color={user?.is_verified ? "success" : "warning"}
                />
                <StatCard
                    label="Multi-factor auth"
                    value={user?.mfa_enabled ? "Enabled" : "Not enabled"}
                    description="Additional sign-in protection"
                    icon={<SecurityIcon />}
                    loading={userLoading}
                    color={user?.mfa_enabled ? "success" : "secondary"}
                />
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.25fr) minmax(320px, 0.9fr)" },
                }}
            >
                <SectionCard
                    title="Recent activity"
                    description="The latest notifications and alerts across your account."
                    action={
                        <Button variant="text" onClick={() => navigate("/notifications")}>
                            Open all
                        </Button>
                    }
                >
                    {notificationsLoading ? (
                        <Stack spacing={1.5}>
                            {Array.from({ length: 4 }).map((_, index) => (
                                <Skeleton key={index} variant="rounded" height={92} sx={{ borderRadius: 4 }} />
                            ))}
                        </Stack>
                    ) : recentNotifications.length === 0 ? (
                        <EmptyState
                            icon={<NotificationsIcon />}
                            title="No notifications yet"
                            description="Updates, reminders, and account events will appear here as soon as the workspace becomes active."
                            action={
                                <Button variant="outlined" onClick={() => navigate("/projects")}>
                                    Explore workspace
                                </Button>
                            }
                        />
                    ) : (
                        <Stack spacing={1.5}>
                            {recentNotifications.map((notification) => (
                                <Box
                                    key={notification.id}
                                    sx={(theme) => ({
                                        border: `1px solid ${theme.palette.divider}`,
                                        borderRadius: 4,
                                        px: 2,
                                        py: 1.75,
                                        backgroundColor: notification.is_read
                                            ? "transparent"
                                            : alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.14 : 0.07),
                                    })}
                                >
                                    <Stack
                                        direction={{ xs: "column", sm: "row" }}
                                        justifyContent="space-between"
                                        spacing={1}
                                    >
                                        <Box>
                                            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                                                <Typography variant="subtitle2">{notification.title}</Typography>
                                                {!notification.is_read && <Chip label="New" size="small" color="primary" />}
                                            </Stack>
                                            {notification.body && (
                                                <Typography variant="body2" color="text.secondary">
                                                    {notification.body}
                                                </Typography>
                                            )}
                                        </Box>
                                        <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
                                            {formatDateTime(notification.created_at)}
                                        </Typography>
                                    </Stack>
                                </Box>
                            ))}
                        </Stack>
                    )}
                </SectionCard>

                <Stack spacing={2}>
                    <SectionCard title="Account health" description="A quick view of the settings that affect trust and security.">
                        <Stack spacing={1.5}>
                            {accountChecks.map((item) => (
                                <Box
                                    key={item.label}
                                    sx={(theme) => ({
                                        p: 2,
                                        borderRadius: 4,
                                        border: `1px solid ${theme.palette.divider}`,
                                        backgroundColor: theme.palette.background.paper,
                                    })}
                                >
                                    <Stack direction="row" justifyContent="space-between" spacing={1} sx={{ mb: 0.5 }}>
                                        <Typography variant="subtitle2">{item.label}</Typography>
                                        {userLoading ? (
                                            <Skeleton variant="rounded" width={96} height={28} />
                                        ) : (
                                            <Typography variant="body2" sx={{ color: item.color, fontWeight: 800 }}>
                                                {item.value}
                                            </Typography>
                                        )}
                                    </Stack>
                                    <Typography variant="body2" color="text.secondary">
                                        {item.description}
                                    </Typography>
                                </Box>
                            ))}
                        </Stack>
                    </SectionCard>

                    <DashboardCalendar
                        projects={projects ?? []}
                        projectsLoading={projectsLoading}
                        onOpenProjects={() => navigate("/projects")}
                        allowedViews={["month"]}
                        initialView="month"
                    />

                    <SectionCard
                        title={`${coreDomainPlural} snapshot`}
                        description={`A quick look at the current ${coreDomainPlural.toLowerCase()} in your workspace.`}
                    >
                        {projectsLoading ? (
                            <Stack spacing={1.25}>
                                {Array.from({ length: 3 }).map((_, index) => (
                                    <Skeleton key={index} variant="rounded" height={72} sx={{ borderRadius: 3 }} />
                                ))}
                            </Stack>
                        ) : projects && projects.length > 0 ? (
                            <Stack spacing={1.25}>
                                {projects.slice(0, 3).map((project) => (
                                    <Box
                                        key={project.id}
                                        sx={(theme) => ({
                                            p: 2,
                                            borderRadius: 3,
                                            border: `1px solid ${theme.palette.divider}`,
                                        })}
                                    >
                                        <Typography variant="subtitle2">{project.name}</Typography>
                                        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                                            {project.description || `No description added for this ${platformMetadata?.core_domain_singular?.toLowerCase() ?? "project"} yet.`}
                                        </Typography>
                                    </Box>
                                ))}
                            </Stack>
                        ) : (
                            <EmptyState
                                icon={<ProjectsIcon />}
                                title={`No ${coreDomainPlural.toLowerCase()} yet`}
                                description={`Create your first ${platformMetadata?.core_domain_singular?.toLowerCase() ?? "project"} to start building out the workspace.`}
                                action={
                                    <Button variant="contained" onClick={() => navigate("/projects")}>
                                        Create first item
                                    </Button>
                                }
                            />
                        )}
                    </SectionCard>
                </Stack>
            </Box>
        </PageShell>
    );
}
