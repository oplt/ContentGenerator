import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    FormControlLabel,
    Skeleton,
    Stack,
    Switch,
    Typography,
} from "@mui/material";
import {
    DoneAll as DoneAllIcon,
    MailOutline as MailOutlineIcon,
    NotificationsActive as NotificationsActiveIcon,
    Campaign as CampaignIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import {
    getNotifications,
    getPreferences,
    markAllRead,
    markRead,
    updatePreferences,
} from "../api/notifications";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { formatDateTime, humanizeKey } from "../utils/formatters";

function PreferenceItem({
    label,
    description,
    checked,
    disabled,
    onChange,
}: {
    label: string;
    description: string;
    checked: boolean;
    disabled: boolean;
    onChange: (nextValue: boolean) => void;
}) {
    return (
        <Box
            sx={(theme) => ({
                p: 2,
                borderRadius: 4,
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: theme.palette.background.paper,
            })}
        >
            <FormControlLabel
                sx={{ alignItems: "flex-start", m: 0, width: "100%" }}
                control={
                    <Switch
                        checked={checked}
                        onChange={(event) => onChange(event.target.checked)}
                        disabled={disabled}
                    />
                }
                label={
                    <Box sx={{ ml: 1 }}>
                        <Typography variant="subtitle2">{label}</Typography>
                        <Typography variant="body2" color="text.secondary">
                            {description}
                        </Typography>
                    </Box>
                }
            />
        </Box>
    );
}

export default function NotificationsPage() {
    const queryClient = useQueryClient();
    const { data: notifications, isLoading, error } = useQuery({
        queryKey: ["notifications"],
        queryFn: getNotifications,
    });
    const { data: prefs } = useQuery({
        queryKey: ["notification-preferences"],
        queryFn: getPreferences,
    });

    const markOneMutation = useMutation({
        mutationFn: markRead,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    });
    const markAllMutation = useMutation({
        mutationFn: markAllRead,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    });
    const prefsMutation = useMutation({
        mutationFn: updatePreferences,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["notification-preferences"] }),
    });

    const unreadCount = notifications?.filter((item) => !item.is_read).length ?? 0;
    const totalCount = notifications?.length ?? 0;
    const enabledChannels = [
        prefs?.email_enabled,
        prefs?.push_enabled,
        prefs?.marketing_enabled,
    ].filter(Boolean).length;

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Signal center"
                title="Notifications"
                description="Stay on top of product activity, account events, and delivery preferences with a clearer inbox and faster controls."
                actions={
                    unreadCount > 0 ? (
                        <Button
                            variant="contained"
                            startIcon={<DoneAllIcon />}
                            disabled={markAllMutation.isPending}
                            onClick={() => markAllMutation.mutate()}
                        >
                            {markAllMutation.isPending ? "Updating..." : "Mark all read"}
                        </Button>
                    ) : undefined
                }
                meta={
                    <>
                        <Chip label={`${unreadCount} unread`} color={unreadCount > 0 ? "primary" : "default"} variant="outlined" />
                        <Chip label={`${totalCount} total`} variant="outlined" />
                    </>
                }
            />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", md: "repeat(3, minmax(0, 1fr))" },
                }}
            >
                <StatCard
                    label="Unread"
                    value={unreadCount}
                    description="Fresh activity that still needs attention"
                    icon={<NotificationsActiveIcon />}
                    loading={isLoading}
                />
                <StatCard
                    label="All notifications"
                    value={totalCount}
                    description="Historical inbox items available for review"
                    icon={<MailOutlineIcon />}
                    loading={isLoading}
                    color="secondary"
                />
                <StatCard
                    label="Channels enabled"
                    value={`${enabledChannels}/3`}
                    description="Delivery routes currently turned on"
                    icon={<CampaignIcon />}
                    color="success"
                />
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.25fr) minmax(320px, 0.85fr)" },
                }}
            >
                <SectionCard title="Inbox" description="Messages are sorted for fast scanning and clear read state.">
                    {error && (
                        <Alert severity="error" sx={{ mb: 2 }}>
                            {error instanceof Error ? error.message : "Failed to load notifications."}
                        </Alert>
                    )}

                    {isLoading ? (
                        <Stack spacing={1.5}>
                            {Array.from({ length: 5 }).map((_, index) => (
                                <Skeleton key={index} variant="rounded" height={102} sx={{ borderRadius: 4 }} />
                            ))}
                        </Stack>
                    ) : notifications && notifications.length > 0 ? (
                        <Stack spacing={1.5}>
                            {notifications.map((notification) => {
                                const isUpdatingThisItem =
                                    markOneMutation.isPending &&
                                    markOneMutation.variables === notification.id;
                                return (
                                    <Box
                                        key={notification.id}
                                        sx={(theme) => ({
                                            p: 2.25,
                                            borderRadius: 4,
                                            border: `1px solid ${theme.palette.divider}`,
                                            backgroundColor: notification.is_read
                                                ? alpha(theme.palette.background.paper, 0.68)
                                                : alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.16 : 0.06),
                                        })}
                                    >
                                        <Stack spacing={1.25}>
                                            <Stack
                                                direction={{ xs: "column", sm: "row" }}
                                                justifyContent="space-between"
                                                spacing={1.5}
                                            >
                                                <Box>
                                                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                        <Typography variant="subtitle2">{notification.title}</Typography>
                                                        <Chip label={humanizeKey(notification.type)} size="small" variant="outlined" />
                                                        {!notification.is_read && <Chip label="New" size="small" color="primary" />}
                                                    </Stack>
                                                </Box>
                                                <Typography variant="caption" color="text.secondary">
                                                    {formatDateTime(notification.created_at)}
                                                </Typography>
                                            </Stack>
                                            {notification.body && (
                                                <Typography variant="body2" color="text.secondary">
                                                    {notification.body}
                                                </Typography>
                                            )}
                                            {!notification.is_read && (
                                                <Box>
                                                    <Button
                                                        size="small"
                                                        variant="outlined"
                                                        disabled={isUpdatingThisItem}
                                                        onClick={() => markOneMutation.mutate(notification.id)}
                                                    >
                                                        {isUpdatingThisItem ? "Saving..." : "Mark as read"}
                                                    </Button>
                                                </Box>
                                            )}
                                        </Stack>
                                    </Box>
                                );
                            })}
                        </Stack>
                    ) : (
                        <EmptyState
                            icon={<NotificationsActiveIcon />}
                            title="Inbox is clear"
                            description="You have no notifications yet. New product updates and account events will appear here."
                        />
                    )}
                </SectionCard>

                <SectionCard title="Delivery preferences" description="Choose how you want this workspace to reach you.">
                    <Stack spacing={1.5}>
                        <PreferenceItem
                            label="Email notifications"
                            description="Receive operational updates and account messages in your inbox."
                            checked={prefs?.email_enabled ?? true}
                            disabled={prefsMutation.isPending}
                            onChange={(nextValue) => prefsMutation.mutate({ email_enabled: nextValue })}
                        />
                        <PreferenceItem
                            label="Push notifications"
                            description="Surface urgent activity directly inside the app experience."
                            checked={prefs?.push_enabled ?? true}
                            disabled={prefsMutation.isPending}
                            onChange={(nextValue) => prefsMutation.mutate({ push_enabled: nextValue })}
                        />
                        <PreferenceItem
                            label="Marketing emails"
                            description="Get launch announcements, feature roundups, and educational updates."
                            checked={prefs?.marketing_enabled ?? false}
                            disabled={prefsMutation.isPending}
                            onChange={(nextValue) => prefsMutation.mutate({ marketing_enabled: nextValue })}
                        />
                    </Stack>
                </SectionCard>
            </Box>
        </PageShell>
    );
}
