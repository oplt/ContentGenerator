import { useState } from "react";
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
    TextField,
    Typography,
} from "@mui/material";
import {
    Bolt as BillingIcon,
    Flag as FlagIcon,
    Key as KeyIcon,
    Link as LinkIcon,
    Webhook as WebhookIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import {
    createApiKey,
    createWebhook,
    deleteWebhook,
    getMySubscription,
    listApiKeys,
    listMyFeatureFlags,
    listSubscriptionPlans,
    listWebhooks,
    revokeApiKey,
    selectMyPlan,
    testWebhook,
    updateWebhook,
} from "../api/platform";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { usePlatformMetadata } from "../hooks/usePlatformMetadata";
import { formatCurrency, formatDateTime } from "../utils/formatters";

export default function PlatformPage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const { data: metadata, isLoading: metadataLoading } = usePlatformMetadata();
    const enabledModules = metadata?.enabled_modules ?? [];
    const billingEnabled = enabledModules.includes("billing");
    const apiKeysEnabled = enabledModules.includes("api_keys");
    const webhooksEnabled = enabledModules.includes("webhooks");
    const flagsEnabled = enabledModules.includes("feature_flags");

    const { data: plans, isLoading: plansLoading } = useQuery({
        queryKey: ["platform", "plans"],
        queryFn: listSubscriptionPlans,
        enabled: billingEnabled,
    });
    const { data: subscription, isLoading: subscriptionLoading } = useQuery({
        queryKey: ["platform", "subscription"],
        queryFn: getMySubscription,
        enabled: billingEnabled,
    });
    const { data: apiKeys, isLoading: apiKeysLoading } = useQuery({
        queryKey: ["platform", "api-keys"],
        queryFn: listApiKeys,
        enabled: apiKeysEnabled,
    });
    const { data: webhooks, isLoading: webhooksLoading } = useQuery({
        queryKey: ["platform", "webhooks"],
        queryFn: listWebhooks,
        enabled: webhooksEnabled,
    });
    const { data: featureFlags, isLoading: featureFlagsLoading } = useQuery({
        queryKey: ["platform", "feature-flags"],
        queryFn: listMyFeatureFlags,
        enabled: flagsEnabled,
    });

    const [apiKeyName, setApiKeyName] = useState("");
    const [revealedKey, setRevealedKey] = useState<string | null>(null);
    const [webhookDraft, setWebhookDraft] = useState({
        target_url: "",
        description: "",
        events: "platform.test",
    });
    const [lastWebhookResult, setLastWebhookResult] = useState("");

    const selectPlanMutation = useMutation({
        mutationFn: selectMyPlan,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform", "subscription"] });
            showToast({ message: "Subscription updated.", severity: "success" });
        },
        onError: (error) => {
            showToast({
                message: error instanceof Error ? error.message : "Failed to update subscription.",
                severity: "error",
            });
        },
    });
    const createApiKeyMutation = useMutation({
        mutationFn: createApiKey,
        onSuccess: async (data) => {
            setApiKeyName("");
            setRevealedKey(data.plaintext_key);
            await queryClient.invalidateQueries({ queryKey: ["platform", "api-keys"] });
        },
    });
    const revokeApiKeyMutation = useMutation({
        mutationFn: revokeApiKey,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform", "api-keys"] });
            showToast({ message: "API key revoked.", severity: "success" });
        },
    });
    const createWebhookMutation = useMutation({
        mutationFn: createWebhook,
        onSuccess: async () => {
            setWebhookDraft({ target_url: "", description: "", events: "platform.test" });
            await queryClient.invalidateQueries({ queryKey: ["platform", "webhooks"] });
            showToast({ message: "Webhook created.", severity: "success" });
        },
    });
    const toggleWebhookMutation = useMutation({
        mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
            updateWebhook(id, { is_active }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform", "webhooks"] });
        },
    });
    const deleteWebhookMutation = useMutation({
        mutationFn: deleteWebhook,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform", "webhooks"] });
            showToast({ message: "Webhook deleted.", severity: "success" });
        },
    });
    const testWebhookMutation = useMutation({
        mutationFn: testWebhook,
        onSuccess: (result) => {
            setLastWebhookResult(
                result.delivered
                    ? `Delivered with status ${result.status_code}.`
                    : result.error
                        ? `Delivery failed: ${result.error}`
                        : `Received status ${result.status_code}.`
            );
        },
    });

    if (metadataLoading) {
        return (
            <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
                <Skeleton variant="rounded" width="90%" height={320} sx={{ borderRadius: 6 }} />
            </Box>
        );
    }

    const visibleUserModules =
        metadata?.module_catalog.filter((item) => item.user_visible && item.enabled) ?? [];

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Platform services"
                title="Platform"
                description="Use the optional modules enabled by your current pack, including billing, developer access, event delivery, and feature access."
                meta={
                    <>
                        <Chip label={`Pack: ${metadata?.module_pack ?? "n/a"}`} variant="outlined" />
                        <Chip label={`${visibleUserModules.length} user modules`} variant="outlined" />
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
                    label="Current plan"
                    value={subscription?.plan.name ?? "No plan"}
                    description="Subscription tier currently selected"
                    icon={<BillingIcon />}
                    loading={billingEnabled && subscriptionLoading}
                />
                <StatCard
                    label="API keys"
                    value={apiKeys?.length ?? 0}
                    description="Developer credentials available"
                    icon={<KeyIcon />}
                    loading={apiKeysEnabled && apiKeysLoading}
                    color="secondary"
                />
                <StatCard
                    label="Webhooks"
                    value={webhooks?.length ?? 0}
                    description="Outbound delivery endpoints configured"
                    icon={<WebhookIcon />}
                    loading={webhooksEnabled && webhooksLoading}
                    color="warning"
                />
                <StatCard
                    label="Feature flags"
                    value={featureFlags?.filter((flag) => flag.effective_enabled).length ?? 0}
                    description="Flags currently enabled for your account"
                    icon={<FlagIcon />}
                    loading={flagsEnabled && featureFlagsLoading}
                    color="success"
                />
            </Box>

            {visibleUserModules.length === 0 && (
                <Alert severity="info">
                    The active module pack does not expose any end-user platform modules right now.
                </Alert>
            )}

            {billingEnabled && (
                <SectionCard title="Billing" description="Review plans and switch when your usage changes.">
                    {subscriptionLoading || plansLoading ? (
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: {
                                    xs: "1fr",
                                    sm: "repeat(2, minmax(0, 1fr))",
                                    lg: "repeat(3, minmax(0, 1fr))",
                                },
                            }}
                        >
                            {Array.from({ length: 3 }).map((_, index) => (
                                <Skeleton key={index} variant="rounded" height={200} sx={{ borderRadius: 4 }} />
                            ))}
                        </Box>
                    ) : (
                        <Stack spacing={2}>
                            <Alert severity="info">
                                Current plan: {subscription?.plan.name ?? "No plan selected"}
                            </Alert>
                            <Box
                                sx={{
                                    display: "grid",
                                    gap: 1.5,
                                    gridTemplateColumns: {
                                        xs: "1fr",
                                        sm: "repeat(2, minmax(0, 1fr))",
                                        lg: "repeat(3, minmax(0, 1fr))",
                                    },
                                }}
                            >
                                {plans?.map((plan) => {
                                    const isCurrentPlan = subscription?.plan.code === plan.code;
                                    return (
                                        <Box
                                            key={plan.id}
                                            sx={(theme) => ({
                                                p: 2.5,
                                                borderRadius: 4,
                                                border: `1px solid ${theme.palette.divider}`,
                                                backgroundColor: isCurrentPlan
                                                    ? alpha(theme.palette.primary.main, theme.palette.mode === "dark" ? 0.18 : 0.06)
                                                    : theme.palette.background.paper,
                                                height: "100%",
                                            })}
                                        >
                                            <Stack spacing={1.5}>
                                                <Stack
                                                    direction={{ xs: "column", xl: "row" }}
                                                    justifyContent="space-between"
                                                    spacing={1.5}
                                                >
                                                    <Box>
                                                        <Typography variant="h6">{plan.name}</Typography>
                                                        <Typography variant="body2" color="text.secondary">
                                                            {plan.description || "Subscription plan"}
                                                        </Typography>
                                                    </Box>
                                                    <Typography variant="subtitle1">
                                                        {formatCurrency(plan.price_cents)}/{plan.interval}
                                                    </Typography>
                                                </Stack>
                                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                    {plan.features.map((feature) => (
                                                        <Chip key={feature} label={feature} size="small" variant="outlined" />
                                                    ))}
                                                </Stack>
                                                <Button
                                                    variant={isCurrentPlan ? "outlined" : "contained"}
                                                    disabled={selectPlanMutation.isPending || isCurrentPlan}
                                                    onClick={() => selectPlanMutation.mutate(plan.code)}
                                                >
                                                    {isCurrentPlan ? "Current plan" : "Switch plan"}
                                                </Button>
                                            </Stack>
                                        </Box>
                                    );
                                })}
                            </Box>
                        </Stack>
                    )}
                </SectionCard>
            )}

            {apiKeysEnabled && (
                <SectionCard title="API keys" description="Create and revoke developer credentials with cleaner visibility.">
                    <Stack spacing={2}>
                        {revealedKey && (
                            <Alert severity="success">
                                New key: <Typography component="span" sx={{ fontFamily: '"IBM Plex Mono", monospace' }}>{revealedKey}</Typography>. Copy it now. It will not be shown again.
                            </Alert>
                        )}
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
                            <TextField
                                label="Key name"
                                value={apiKeyName}
                                onChange={(event) => setApiKeyName(event.target.value)}
                                fullWidth
                            />
                            <Button
                                variant="contained"
                                disabled={createApiKeyMutation.isPending || apiKeyName.trim().length < 2}
                                onClick={() => createApiKeyMutation.mutate(apiKeyName.trim())}
                            >
                                {createApiKeyMutation.isPending ? "Creating..." : "Create key"}
                            </Button>
                        </Stack>
                        {apiKeysLoading ? (
                            <Stack spacing={1.25}>
                                {Array.from({ length: 3 }).map((_, index) => (
                                    <Skeleton key={index} variant="rounded" height={92} sx={{ borderRadius: 4 }} />
                                ))}
                            </Stack>
                        ) : apiKeys && apiKeys.length > 0 ? (
                            <Stack spacing={1.25}>
                                {apiKeys.map((apiKey) => {
                                    const isRevokingThisKey =
                                        revokeApiKeyMutation.isPending &&
                                        revokeApiKeyMutation.variables === apiKey.id;
                                    return (
                                        <Box
                                            key={apiKey.id}
                                            sx={(theme) => ({
                                                p: 2.25,
                                                borderRadius: 4,
                                                border: `1px solid ${theme.palette.divider}`,
                                            })}
                                        >
                                            <Stack
                                                direction={{ xs: "column", sm: "row" }}
                                                justifyContent="space-between"
                                                spacing={1.5}
                                            >
                                                <Box>
                                                    <Typography variant="subtitle2">{apiKey.name}</Typography>
                                                    <Typography
                                                        variant="body2"
                                                        color="text.secondary"
                                                        sx={{ fontFamily: '"IBM Plex Mono", monospace' }}
                                                    >
                                                        Prefix {apiKey.key_prefix}
                                                    </Typography>
                                                    <Typography variant="caption" color="text.secondary">
                                                        Created {formatDateTime(apiKey.created_at)}
                                                        {apiKey.last_used_at ? ` • Last used ${formatDateTime(apiKey.last_used_at)}` : ""}
                                                    </Typography>
                                                </Box>
                                                <Button
                                                    variant="outlined"
                                                    color="error"
                                                    disabled={Boolean(apiKey.revoked_at) || isRevokingThisKey}
                                                    onClick={() => revokeApiKeyMutation.mutate(apiKey.id)}
                                                >
                                                    {apiKey.revoked_at ? "Revoked" : isRevokingThisKey ? "Revoking..." : "Revoke"}
                                                </Button>
                                            </Stack>
                                        </Box>
                                    );
                                })}
                            </Stack>
                        ) : (
                            <EmptyState
                                icon={<KeyIcon />}
                                title="No API keys yet"
                                description="Create a key when you are ready to integrate external systems or automation."
                            />
                        )}
                    </Stack>
                </SectionCard>
            )}

            {webhooksEnabled && (
                <SectionCard title="Webhooks" description="Configure delivery endpoints for outbound platform events.">
                    <Stack spacing={2}>
                        {lastWebhookResult && <Alert severity="info">{lastWebhookResult}</Alert>}
                        <Box
                            sx={{
                                display: "grid",
                                gap: 2,
                                gridTemplateColumns: { xs: "1fr", lg: "minmax(320px, 0.9fr) minmax(0, 1.1fr)" },
                            }}
                        >
                            <Stack spacing={1.5}>
                                <TextField
                                    label="Target URL"
                                    value={webhookDraft.target_url}
                                    onChange={(event) =>
                                        setWebhookDraft((current) => ({ ...current, target_url: event.target.value }))
                                    }
                                    fullWidth
                                />
                                <TextField
                                    label="Description"
                                    value={webhookDraft.description}
                                    onChange={(event) =>
                                        setWebhookDraft((current) => ({ ...current, description: event.target.value }))
                                    }
                                    fullWidth
                                />
                                <TextField
                                    label="Events"
                                    value={webhookDraft.events}
                                    onChange={(event) =>
                                        setWebhookDraft((current) => ({ ...current, events: event.target.value }))
                                    }
                                    fullWidth
                                    helperText="Comma-separated event names"
                                />
                                <Button
                                    variant="contained"
                                    disabled={createWebhookMutation.isPending || webhookDraft.target_url.trim().length < 8}
                                    onClick={() =>
                                        createWebhookMutation.mutate({
                                            target_url: webhookDraft.target_url.trim(),
                                            description: webhookDraft.description.trim() || undefined,
                                            events: webhookDraft.events
                                                .split(",")
                                                .map((item) => item.trim())
                                                .filter(Boolean),
                                        })
                                    }
                                >
                                    {createWebhookMutation.isPending ? "Creating..." : "Create webhook"}
                                </Button>
                            </Stack>

                            {webhooksLoading ? (
                                <Stack spacing={1.25}>
                                    {Array.from({ length: 2 }).map((_, index) => (
                                        <Skeleton key={index} variant="rounded" height={148} sx={{ borderRadius: 4 }} />
                                    ))}
                                </Stack>
                            ) : webhooks && webhooks.length > 0 ? (
                                <Stack spacing={1.25}>
                                    {webhooks.map((webhook) => {
                                        const isTestingThisWebhook =
                                            testWebhookMutation.isPending &&
                                            testWebhookMutation.variables === webhook.id;
                                        const isDeletingThisWebhook =
                                            deleteWebhookMutation.isPending &&
                                            deleteWebhookMutation.variables === webhook.id;
                                        const isTogglingThisWebhook =
                                            toggleWebhookMutation.isPending &&
                                            toggleWebhookMutation.variables?.id === webhook.id;

                                        return (
                                            <Box
                                                key={webhook.id}
                                                sx={(theme) => ({
                                                    p: 2.25,
                                                    borderRadius: 4,
                                                    border: `1px solid ${theme.palette.divider}`,
                                                })}
                                            >
                                                <Stack spacing={1.5}>
                                                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
                                                        <Box>
                                                            <Typography variant="subtitle2">{webhook.target_url}</Typography>
                                                            {webhook.description && (
                                                                <Typography variant="body2" color="text.secondary">
                                                                    {webhook.description}
                                                                </Typography>
                                                            )}
                                                        </Box>
                                                        <FormControlLabel
                                                            control={
                                                                <Switch
                                                                    checked={webhook.is_active}
                                                                    disabled={isTogglingThisWebhook}
                                                                    onChange={(event) =>
                                                                        toggleWebhookMutation.mutate({
                                                                            id: webhook.id,
                                                                            is_active: event.target.checked,
                                                                        })
                                                                    }
                                                                />
                                                            }
                                                            label="Active"
                                                        />
                                                    </Stack>
                                                    <Typography
                                                        variant="body2"
                                                        color="text.secondary"
                                                        sx={{ fontFamily: '"IBM Plex Mono", monospace' }}
                                                    >
                                                        Secret: {webhook.secret}
                                                    </Typography>
                                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                        {webhook.events.map((eventName) => (
                                                            <Chip key={eventName} label={eventName} size="small" />
                                                        ))}
                                                    </Stack>
                                                    <Typography variant="caption" color="text.secondary">
                                                        {webhook.last_tested_at
                                                            ? `Last tested ${formatDateTime(webhook.last_tested_at)}`
                                                            : "Not tested yet"}
                                                        {webhook.last_response_status
                                                            ? ` • Last status ${webhook.last_response_status}`
                                                            : ""}
                                                    </Typography>
                                                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                                        <Button
                                                            variant="outlined"
                                                            size="small"
                                                            startIcon={<LinkIcon />}
                                                            disabled={isTestingThisWebhook}
                                                            onClick={() => testWebhookMutation.mutate(webhook.id)}
                                                        >
                                                            {isTestingThisWebhook ? "Testing..." : "Test delivery"}
                                                        </Button>
                                                        <Button
                                                            variant="outlined"
                                                            color="error"
                                                            size="small"
                                                            disabled={isDeletingThisWebhook}
                                                            onClick={() => deleteWebhookMutation.mutate(webhook.id)}
                                                        >
                                                            {isDeletingThisWebhook ? "Deleting..." : "Delete"}
                                                        </Button>
                                                    </Stack>
                                                </Stack>
                                            </Box>
                                        );
                                    })}
                                </Stack>
                            ) : (
                                <EmptyState
                                    icon={<WebhookIcon />}
                                    title="No webhooks configured"
                                    description="Create an endpoint to push platform events into your own systems."
                                />
                            )}
                        </Box>
                    </Stack>
                </SectionCard>
            )}

            {flagsEnabled && (
                <SectionCard title="Feature flags" description="These flags are active for your account based on current platform configuration.">
                    {featureFlagsLoading ? (
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                            }}
                        >
                            {Array.from({ length: 3 }).map((_, index) => (
                                <Skeleton key={index} variant="rounded" height={144} sx={{ borderRadius: 4 }} />
                            ))}
                        </Box>
                    ) : featureFlags && featureFlags.length > 0 ? (
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                            }}
                        >
                            {featureFlags.map((flag) => (
                                <Box
                                    key={flag.id}
                                    sx={(theme) => ({
                                        p: 2.25,
                                        borderRadius: 4,
                                        border: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Stack spacing={1}>
                                        <Stack direction="row" justifyContent="space-between" spacing={1}>
                                            <Box>
                                                <Typography variant="subtitle2">{flag.name}</Typography>
                                                <Typography variant="body2" color="text.secondary">
                                                    {flag.key}
                                                </Typography>
                                            </Box>
                                            <Chip
                                                label={flag.effective_enabled ? "Enabled for you" : "Off"}
                                                color={flag.effective_enabled ? "success" : "default"}
                                                size="small"
                                            />
                                        </Stack>
                                        {flag.description && (
                                            <Typography variant="body2" color="text.secondary">
                                                {flag.description}
                                            </Typography>
                                        )}
                                    </Stack>
                                </Box>
                            ))}
                        </Box>
                    ) : (
                        <EmptyState
                            icon={<FlagIcon />}
                            title="No feature flags configured"
                            description="Flags will appear here when the platform exposes rollout-based capabilities."
                        />
                    )}
                </SectionCard>
            )}
        </PageShell>
    );
}
