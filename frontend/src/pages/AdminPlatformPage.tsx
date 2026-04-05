import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    FormControlLabel,
    MenuItem,
    Skeleton,
    Stack,
    Switch,
    TextField,
    Typography,
} from "@mui/material";
import {
    Extension as ExtensionIcon,
    Flag as FlagIcon,
    MailOutline as MailOutlineIcon,
    Sell as SellIcon,
} from "@mui/icons-material";
import {
    createAdminEmailTemplate,
    createAdminFeatureFlag,
    createAdminPlan,
    getPlatformConfig,
    listAdminEmailTemplates,
    listAdminFeatureFlags,
    listAdminPlans,
    updateAdminEmailTemplate,
    updateAdminFeatureFlag,
    updateAdminPlan,
    updatePlatformConfig,
    type EmailTemplate,
    type FeatureFlag,
    type PlatformConfig,
    type SubscriptionPlan,
} from "../api/platform";
import { useSnackbar } from "../app/snackbarContext";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";

type PlanDraft = {
    name: string;
    description: string;
    price_cents: string;
    interval: string;
    is_active: boolean;
    is_default: boolean;
    features: string;
};

type FlagDraft = {
    name: string;
    description: string;
    module_key: string;
    is_enabled: boolean;
    rollout_percentage: string;
};

type TemplateDraft = {
    name: string;
    subject_template: string;
    html_template: string;
    text_template: string;
    is_active: boolean;
};

function buildConfigDraft(configData: PlatformConfig) {
    return {
        app_name: configData.app_name,
        core_domain_singular: configData.core_domain_singular,
        core_domain_plural: configData.core_domain_plural,
        module_pack: configData.module_pack,
        module_states: Object.fromEntries(configData.module_catalog.map((item) => [item.key, item.enabled])),
    };
}

function buildPlanDrafts(plans: SubscriptionPlan[]) {
    return Object.fromEntries(
        plans.map((plan) => [
            plan.id,
            {
                name: plan.name,
                description: plan.description ?? "",
                price_cents: String(plan.price_cents),
                interval: plan.interval,
                is_active: plan.is_active,
                is_default: plan.is_default,
                features: plan.features.join(", "),
            },
        ])
    ) as Record<string, PlanDraft>;
}

function buildFlagDrafts(flags: FeatureFlag[]) {
    return Object.fromEntries(
        flags.map((flag) => [
            flag.id,
            {
                name: flag.name,
                description: flag.description ?? "",
                module_key: flag.module_key ?? "",
                is_enabled: flag.is_enabled,
                rollout_percentage: String(flag.rollout_percentage),
            },
        ])
    ) as Record<string, FlagDraft>;
}

function buildTemplateDrafts(templates: EmailTemplate[]) {
    return Object.fromEntries(
        templates.map((template) => [
            template.id,
            {
                name: template.name,
                subject_template: template.subject_template,
                html_template: template.html_template,
                text_template: template.text_template ?? "",
                is_active: template.is_active,
            },
        ])
    ) as Record<string, TemplateDraft>;
}

function AdminPlatformContent({
    configData,
    plans,
    flags,
    templates,
}: {
    configData: PlatformConfig;
    plans: SubscriptionPlan[];
    flags: FeatureFlag[];
    templates: EmailTemplate[];
}) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [configDraft, setConfigDraft] = useState(() => buildConfigDraft(configData));
    const [planDrafts, setPlanDrafts] = useState<Record<string, PlanDraft>>(() => buildPlanDrafts(plans));
    const [flagDrafts, setFlagDrafts] = useState<Record<string, FlagDraft>>(() => buildFlagDrafts(flags));
    const [templateDrafts, setTemplateDrafts] = useState<Record<string, TemplateDraft>>(() => buildTemplateDrafts(templates));
    const [newPlan, setNewPlan] = useState({
        code: "",
        name: "",
        description: "",
        price_cents: "0",
        interval: "month",
        is_default: false,
        features: "",
    });
    const [newFlag, setNewFlag] = useState({
        key: "",
        name: "",
        description: "",
        module_key: "",
        is_enabled: false,
        rollout_percentage: "100",
    });
    const [newTemplate, setNewTemplate] = useState({
        key: "",
        name: "",
        subject_template: "",
        html_template: "",
        text_template: "",
        is_active: true,
    });

    const moduleCatalog = configData.module_catalog;
    const packOptions = configData.available_module_packs;
    const activePackSummary = packOptions.find((pack) => pack.key === configDraft.module_pack);

    const saveConfigMutation = useMutation({
        mutationFn: updatePlatformConfig,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform"] });
            showToast({ message: "Platform configuration updated.", severity: "success" });
        },
    });
    const createPlanMutation = useMutation({
        mutationFn: createAdminPlan,
        onSuccess: async () => {
            setNewPlan({
                code: "",
                name: "",
                description: "",
                price_cents: "0",
                interval: "month",
                is_default: false,
                features: "",
            });
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "plans"] });
            showToast({ message: "Plan created.", severity: "success" });
        },
    });
    const updatePlanMutation = useMutation({
        mutationFn: ({ id, draft }: { id: string; draft: PlanDraft }) =>
            updateAdminPlan(id, {
                name: draft.name,
                description: draft.description || null,
                price_cents: Number(draft.price_cents),
                interval: draft.interval,
                is_active: draft.is_active,
                is_default: draft.is_default,
                features: draft.features.split(",").map((item) => item.trim()).filter(Boolean),
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "plans"] });
            showToast({ message: "Plan updated.", severity: "success" });
        },
    });
    const createFlagMutation = useMutation({
        mutationFn: createAdminFeatureFlag,
        onSuccess: async () => {
            setNewFlag({
                key: "",
                name: "",
                description: "",
                module_key: "",
                is_enabled: false,
                rollout_percentage: "100",
            });
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "feature-flags"] });
            showToast({ message: "Feature flag created.", severity: "success" });
        },
    });
    const updateFlagMutation = useMutation({
        mutationFn: ({ id, draft }: { id: string; draft: FlagDraft }) =>
            updateAdminFeatureFlag(id, {
                name: draft.name,
                description: draft.description || null,
                module_key: draft.module_key || null,
                is_enabled: draft.is_enabled,
                rollout_percentage: Number(draft.rollout_percentage),
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "feature-flags"] });
            showToast({ message: "Feature flag updated.", severity: "success" });
        },
    });
    const createTemplateMutation = useMutation({
        mutationFn: createAdminEmailTemplate,
        onSuccess: async () => {
            setNewTemplate({
                key: "",
                name: "",
                subject_template: "",
                html_template: "",
                text_template: "",
                is_active: true,
            });
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "email-templates"] });
            showToast({ message: "Email template created.", severity: "success" });
        },
    });
    const updateTemplateMutation = useMutation({
        mutationFn: ({ id, draft }: { id: string; draft: TemplateDraft }) =>
            updateAdminEmailTemplate(id, {
                name: draft.name,
                subject_template: draft.subject_template,
                html_template: draft.html_template,
                text_template: draft.text_template || null,
                is_active: draft.is_active,
            }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["platform", "admin", "email-templates"] });
            showToast({ message: "Email template updated.", severity: "success" });
        },
    });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Administration"
                title="Platform admin"
                description="Configure clone defaults, module packs, plans, feature flags, and reusable email templates with clearer grouping and operational feedback."
                meta={
                    <>
                        <Chip label={`${moduleCatalog.length} modules`} variant="outlined" />
                        <Chip label={`${plans.length} plans`} variant="outlined" />
                        <Chip label={`${flags.length} feature flags`} variant="outlined" />
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
                    label="Enabled modules"
                    value={Object.values(configDraft.module_states).filter(Boolean).length}
                    description="Modules currently exposed by the selected pack and overrides"
                    icon={<ExtensionIcon />}
                />
                <StatCard
                    label="Subscription plans"
                    value={plans.length}
                    description="Commercial tiers available across the platform"
                    icon={<SellIcon />}
                    color="secondary"
                />
                <StatCard
                    label="Feature flags"
                    value={flags.length}
                    description="Flags available for rollout and experimentation"
                    icon={<FlagIcon />}
                    color="success"
                />
                <StatCard
                    label="Email templates"
                    value={templates.length}
                    description="Transactional templates ready for automated delivery"
                    icon={<MailOutlineIcon />}
                    color="warning"
                />
            </Box>

            <SectionCard
                title="Clone configuration"
                description="Set the product name, core domain terminology, module pack, and module visibility defaults."
                action={
                    <Button
                        variant="contained"
                        disabled={saveConfigMutation.isPending}
                        onClick={() =>
                            saveConfigMutation.mutate({
                                app_name: configDraft.app_name,
                                core_domain_singular: configDraft.core_domain_singular,
                                core_domain_plural: configDraft.core_domain_plural,
                                module_pack: configDraft.module_pack,
                                module_overrides: configDraft.module_states,
                            })
                        }
                    >
                        {saveConfigMutation.isPending ? "Saving..." : "Save platform config"}
                    </Button>
                }
            >
                <Stack spacing={2.5}>
                    {saveConfigMutation.isError && (
                        <Alert severity="error">
                            {saveConfigMutation.error instanceof Error
                                ? saveConfigMutation.error.message
                                : "Failed to save platform config."}
                        </Alert>
                    )}
                    <TextField
                        label="App name"
                        value={configDraft.app_name}
                        onChange={(event) => setConfigDraft((current) => ({ ...current, app_name: event.target.value }))}
                        fullWidth
                    />
                    <Box
                        sx={{
                            display: "grid",
                            gap: 1.5,
                            gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                        }}
                    >
                        <TextField
                            label="Core domain singular"
                            value={configDraft.core_domain_singular}
                            onChange={(event) =>
                                setConfigDraft((current) => ({
                                    ...current,
                                    core_domain_singular: event.target.value,
                                }))
                            }
                            fullWidth
                        />
                        <TextField
                            label="Core domain plural"
                            value={configDraft.core_domain_plural}
                            onChange={(event) =>
                                setConfigDraft((current) => ({
                                    ...current,
                                    core_domain_plural: event.target.value,
                                }))
                            }
                            fullWidth
                        />
                    </Box>
                    <TextField
                        label="Module pack"
                        select
                        value={configDraft.module_pack}
                        onChange={(event) => {
                            const nextPack = event.target.value;
                            const packDefaults = packOptions.find((pack) => pack.key === nextPack)?.modules ?? [];
                            setConfigDraft((current) => ({
                                ...current,
                                module_pack: nextPack,
                                module_states: Object.fromEntries(
                                    moduleCatalog.map((item) => [item.key, packDefaults.includes(item.key)])
                                ),
                            }));
                        }}
                        fullWidth
                    >
                        {packOptions.map((pack) => (
                            <MenuItem key={pack.key} value={pack.key}>
                                {pack.label}
                            </MenuItem>
                        ))}
                    </TextField>
                    {activePackSummary && <Alert severity="info">{activePackSummary.description}</Alert>}

                    <Box>
                        <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                            Module access
                        </Typography>
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.25,
                                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                            }}
                        >
                            {moduleCatalog.map((moduleItem) => (
                                <Box
                                    key={moduleItem.key}
                                    sx={(theme) => ({
                                        p: 2,
                                        borderRadius: 4,
                                        border: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                                        <Box>
                                            <Typography variant="subtitle2">{moduleItem.label}</Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {moduleItem.description}
                                            </Typography>
                                        </Box>
                                        <Switch
                                            checked={configDraft.module_states[moduleItem.key] ?? false}
                                            onChange={(event) =>
                                                setConfigDraft((current) => ({
                                                    ...current,
                                                    module_states: {
                                                        ...current.module_states,
                                                        [moduleItem.key]: event.target.checked,
                                                    },
                                                }))
                                            }
                                        />
                                    </Stack>
                                </Box>
                            ))}
                        </Box>
                    </Box>
                </Stack>
            </SectionCard>

            <SectionCard title="Subscription plans" description="Create new commercial tiers and tune existing plans.">
                <Stack spacing={2.5}>
                    <Box
                        sx={(theme) => ({
                            p: 2.5,
                            borderRadius: 4,
                            border: `1px solid ${theme.palette.divider}`,
                        })}
                    >
                        <Stack spacing={1.5}>
                            <Typography variant="subtitle2">Create plan</Typography>
                            <Box
                                sx={{
                                    display: "grid",
                                    gap: 1.5,
                                    gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                                }}
                            >
                                <TextField
                                    label="Code"
                                    value={newPlan.code}
                                    onChange={(event) => setNewPlan((current) => ({ ...current, code: event.target.value }))}
                                    fullWidth
                                />
                                <TextField
                                    label="Name"
                                    value={newPlan.name}
                                    onChange={(event) => setNewPlan((current) => ({ ...current, name: event.target.value }))}
                                    fullWidth
                                />
                                <TextField
                                    label="Price (cents)"
                                    value={newPlan.price_cents}
                                    onChange={(event) =>
                                        setNewPlan((current) => ({ ...current, price_cents: event.target.value }))
                                    }
                                    fullWidth
                                />
                                <TextField
                                    label="Interval"
                                    value={newPlan.interval}
                                    onChange={(event) =>
                                        setNewPlan((current) => ({ ...current, interval: event.target.value }))
                                    }
                                    fullWidth
                                />
                            </Box>
                            <TextField
                                label="Description"
                                value={newPlan.description}
                                onChange={(event) =>
                                    setNewPlan((current) => ({ ...current, description: event.target.value }))
                                }
                                fullWidth
                            />
                            <TextField
                                label="Features"
                                value={newPlan.features}
                                onChange={(event) =>
                                    setNewPlan((current) => ({ ...current, features: event.target.value }))
                                }
                                helperText="Comma-separated feature labels"
                                fullWidth
                            />
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={newPlan.is_default}
                                        onChange={(event) =>
                                            setNewPlan((current) => ({ ...current, is_default: event.target.checked }))
                                        }
                                    />
                                }
                                label="Default plan"
                            />
                            <Button
                                variant="contained"
                                disabled={createPlanMutation.isPending || newPlan.code.trim().length < 2}
                                onClick={() =>
                                    createPlanMutation.mutate({
                                        code: newPlan.code.trim(),
                                        name: newPlan.name.trim(),
                                        description: newPlan.description.trim() || undefined,
                                        price_cents: Number(newPlan.price_cents),
                                        interval: newPlan.interval.trim(),
                                        is_default: newPlan.is_default,
                                        features: newPlan.features.split(",").map((item) => item.trim()).filter(Boolean),
                                    })
                                }
                            >
                                {createPlanMutation.isPending ? "Creating..." : "Create plan"}
                            </Button>
                        </Stack>
                    </Box>

                    <Stack spacing={1.5}>
                        {plans.map((plan) => {
                            const draft = planDrafts[plan.id];
                            const isSavingThisPlan =
                                updatePlanMutation.isPending && updatePlanMutation.variables?.id === plan.id;

                            return (
                                <Box
                                    key={plan.id}
                                    sx={(theme) => ({
                                        p: 2.5,
                                        borderRadius: 4,
                                        border: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Stack spacing={1.5}>
                                        <Stack direction="row" spacing={1} alignItems="center">
                                            <Typography variant="subtitle2">{plan.code}</Typography>
                                            {plan.is_default && <Chip label="Default" size="small" color="primary" />}
                                        </Stack>
                                        <Box
                                            sx={{
                                                display: "grid",
                                                gap: 1.5,
                                                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                                            }}
                                        >
                                            <TextField
                                                label="Name"
                                                value={draft.name}
                                                onChange={(event) =>
                                                    setPlanDrafts((current) => ({
                                                        ...current,
                                                        [plan.id]: { ...draft, name: event.target.value },
                                                    }))
                                                }
                                                fullWidth
                                            />
                                            <TextField
                                                label="Price (cents)"
                                                value={draft.price_cents}
                                                onChange={(event) =>
                                                    setPlanDrafts((current) => ({
                                                        ...current,
                                                        [plan.id]: { ...draft, price_cents: event.target.value },
                                                    }))
                                                }
                                                fullWidth
                                            />
                                            <TextField
                                                label="Interval"
                                                value={draft.interval}
                                                onChange={(event) =>
                                                    setPlanDrafts((current) => ({
                                                        ...current,
                                                        [plan.id]: { ...draft, interval: event.target.value },
                                                    }))
                                                }
                                                fullWidth
                                            />
                                            <TextField
                                                label="Features"
                                                value={draft.features}
                                                onChange={(event) =>
                                                    setPlanDrafts((current) => ({
                                                        ...current,
                                                        [plan.id]: { ...draft, features: event.target.value },
                                                    }))
                                                }
                                                fullWidth
                                            />
                                        </Box>
                                        <TextField
                                            label="Description"
                                            value={draft.description}
                                            onChange={(event) =>
                                                setPlanDrafts((current) => ({
                                                    ...current,
                                                    [plan.id]: { ...draft, description: event.target.value },
                                                }))
                                            }
                                            fullWidth
                                        />
                                        <Stack direction="row" spacing={2}>
                                            <FormControlLabel
                                                control={
                                                    <Switch
                                                        checked={draft.is_active}
                                                        onChange={(event) =>
                                                            setPlanDrafts((current) => ({
                                                                ...current,
                                                                [plan.id]: { ...draft, is_active: event.target.checked },
                                                            }))
                                                        }
                                                    />
                                                }
                                                label="Active"
                                            />
                                            <FormControlLabel
                                                control={
                                                    <Switch
                                                        checked={draft.is_default}
                                                        onChange={(event) =>
                                                            setPlanDrafts((current) => ({
                                                                ...current,
                                                                [plan.id]: { ...draft, is_default: event.target.checked },
                                                            }))
                                                        }
                                                    />
                                                }
                                                label="Default"
                                            />
                                        </Stack>
                                        <Button
                                            variant="outlined"
                                            disabled={isSavingThisPlan}
                                            onClick={() => updatePlanMutation.mutate({ id: plan.id, draft })}
                                        >
                                            {isSavingThisPlan ? "Saving..." : "Save plan"}
                                        </Button>
                                    </Stack>
                                </Box>
                            );
                        })}
                    </Stack>
                </Stack>
            </SectionCard>

            <SectionCard title="Feature flags" description="Create rollout controls and tune existing flags.">
                <Stack spacing={2.5}>
                    <Box
                        sx={(theme) => ({
                            p: 2.5,
                            borderRadius: 4,
                            border: `1px solid ${theme.palette.divider}`,
                        })}
                    >
                        <Stack spacing={1.5}>
                            <Typography variant="subtitle2">Create feature flag</Typography>
                            <Box
                                sx={{
                                    display: "grid",
                                    gap: 1.5,
                                    gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                                }}
                            >
                                <TextField
                                    label="Key"
                                    value={newFlag.key}
                                    onChange={(event) => setNewFlag((current) => ({ ...current, key: event.target.value }))}
                                    fullWidth
                                />
                                <TextField
                                    label="Name"
                                    value={newFlag.name}
                                    onChange={(event) => setNewFlag((current) => ({ ...current, name: event.target.value }))}
                                    fullWidth
                                />
                                <TextField
                                    label="Module key"
                                    value={newFlag.module_key}
                                    onChange={(event) =>
                                        setNewFlag((current) => ({ ...current, module_key: event.target.value }))
                                    }
                                    fullWidth
                                />
                                <TextField
                                    label="Rollout %"
                                    value={newFlag.rollout_percentage}
                                    onChange={(event) =>
                                        setNewFlag((current) => ({ ...current, rollout_percentage: event.target.value }))
                                    }
                                    fullWidth
                                />
                            </Box>
                            <TextField
                                label="Description"
                                value={newFlag.description}
                                onChange={(event) =>
                                    setNewFlag((current) => ({ ...current, description: event.target.value }))
                                }
                                fullWidth
                            />
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={newFlag.is_enabled}
                                        onChange={(event) =>
                                            setNewFlag((current) => ({ ...current, is_enabled: event.target.checked }))
                                        }
                                    />
                                }
                                label="Enabled"
                            />
                            <Button
                                variant="contained"
                                disabled={createFlagMutation.isPending || newFlag.key.trim().length < 2}
                                onClick={() =>
                                    createFlagMutation.mutate({
                                        key: newFlag.key.trim(),
                                        name: newFlag.name.trim(),
                                        description: newFlag.description.trim() || undefined,
                                        module_key: newFlag.module_key.trim() || null,
                                        is_enabled: newFlag.is_enabled,
                                        rollout_percentage: Number(newFlag.rollout_percentage),
                                    })
                                }
                            >
                                {createFlagMutation.isPending ? "Creating..." : "Create flag"}
                            </Button>
                        </Stack>
                    </Box>

                    <Stack spacing={1.5}>
                        {flags.map((flag) => {
                            const draft = flagDrafts[flag.id];
                            const isSavingThisFlag =
                                updateFlagMutation.isPending && updateFlagMutation.variables?.id === flag.id;

                            return (
                                <Box
                                    key={flag.id}
                                    sx={(theme) => ({
                                        p: 2.5,
                                        borderRadius: 4,
                                        border: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Stack spacing={1.5}>
                                        <Typography variant="subtitle2">{flag.key}</Typography>
                                        <Box
                                            sx={{
                                                display: "grid",
                                                gap: 1.5,
                                                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                                            }}
                                        >
                                            <TextField
                                                label="Name"
                                                value={draft.name}
                                                onChange={(event) =>
                                                    setFlagDrafts((current) => ({
                                                        ...current,
                                                        [flag.id]: { ...draft, name: event.target.value },
                                                    }))
                                                }
                                                fullWidth
                                            />
                                            <TextField
                                                label="Module key"
                                                value={draft.module_key}
                                                onChange={(event) =>
                                                    setFlagDrafts((current) => ({
                                                        ...current,
                                                        [flag.id]: { ...draft, module_key: event.target.value },
                                                    }))
                                                }
                                                fullWidth
                                            />
                                            <TextField
                                                label="Rollout %"
                                                value={draft.rollout_percentage}
                                                onChange={(event) =>
                                                    setFlagDrafts((current) => ({
                                                        ...current,
                                                        [flag.id]: { ...draft, rollout_percentage: event.target.value },
                                                    }))
                                                }
                                                fullWidth
                                            />
                                        </Box>
                                        <TextField
                                            label="Description"
                                            value={draft.description}
                                            onChange={(event) =>
                                                setFlagDrafts((current) => ({
                                                    ...current,
                                                    [flag.id]: { ...draft, description: event.target.value },
                                                }))
                                            }
                                            fullWidth
                                        />
                                        <FormControlLabel
                                            control={
                                                <Switch
                                                    checked={draft.is_enabled}
                                                    onChange={(event) =>
                                                        setFlagDrafts((current) => ({
                                                            ...current,
                                                            [flag.id]: { ...draft, is_enabled: event.target.checked },
                                                        }))
                                                    }
                                                />
                                            }
                                            label="Enabled"
                                        />
                                        <Button
                                            variant="outlined"
                                            disabled={isSavingThisFlag}
                                            onClick={() => updateFlagMutation.mutate({ id: flag.id, draft })}
                                        >
                                            {isSavingThisFlag ? "Saving..." : "Save flag"}
                                        </Button>
                                    </Stack>
                                </Box>
                            );
                        })}
                    </Stack>
                </Stack>
            </SectionCard>

            <SectionCard title="Email templates" description="Create and update reusable transactional email templates.">
                <Stack spacing={2.5}>
                    <Box
                        sx={(theme) => ({
                            p: 2.5,
                            borderRadius: 4,
                            border: `1px solid ${theme.palette.divider}`,
                        })}
                    >
                        <Stack spacing={1.5}>
                            <Typography variant="subtitle2">Create template</Typography>
                            <Box
                                sx={{
                                    display: "grid",
                                    gap: 1.5,
                                    gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                                }}
                            >
                                <TextField
                                    label="Key"
                                    value={newTemplate.key}
                                    onChange={(event) => setNewTemplate((current) => ({ ...current, key: event.target.value }))}
                                    fullWidth
                                />
                                <TextField
                                    label="Name"
                                    value={newTemplate.name}
                                    onChange={(event) => setNewTemplate((current) => ({ ...current, name: event.target.value }))}
                                    fullWidth
                                />
                            </Box>
                            <TextField
                                label="Subject"
                                value={newTemplate.subject_template}
                                onChange={(event) =>
                                    setNewTemplate((current) => ({ ...current, subject_template: event.target.value }))
                                }
                                fullWidth
                            />
                            <TextField
                                label="HTML body"
                                value={newTemplate.html_template}
                                onChange={(event) =>
                                    setNewTemplate((current) => ({ ...current, html_template: event.target.value }))
                                }
                                fullWidth
                                multiline
                                minRows={4}
                            />
                            <TextField
                                label="Text body"
                                value={newTemplate.text_template}
                                onChange={(event) =>
                                    setNewTemplate((current) => ({ ...current, text_template: event.target.value }))
                                }
                                fullWidth
                                multiline
                                minRows={3}
                            />
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={newTemplate.is_active}
                                        onChange={(event) =>
                                            setNewTemplate((current) => ({ ...current, is_active: event.target.checked }))
                                        }
                                    />
                                }
                                label="Active"
                            />
                            <Button
                                variant="contained"
                                disabled={createTemplateMutation.isPending || newTemplate.key.trim().length < 2}
                                onClick={() =>
                                    createTemplateMutation.mutate({
                                        key: newTemplate.key.trim(),
                                        name: newTemplate.name.trim(),
                                        subject_template: newTemplate.subject_template,
                                        html_template: newTemplate.html_template,
                                        text_template: newTemplate.text_template || null,
                                        is_active: newTemplate.is_active,
                                    })
                                }
                            >
                                {createTemplateMutation.isPending ? "Creating..." : "Create template"}
                            </Button>
                        </Stack>
                    </Box>

                    <Stack spacing={1.5}>
                        {templates.map((template) => {
                            const draft = templateDrafts[template.id];
                            const isSavingThisTemplate =
                                updateTemplateMutation.isPending && updateTemplateMutation.variables?.id === template.id;

                            return (
                                <Box
                                    key={template.id}
                                    sx={(theme) => ({
                                        p: 2.5,
                                        borderRadius: 4,
                                        border: `1px solid ${theme.palette.divider}`,
                                    })}
                                >
                                    <Stack spacing={1.5}>
                                        <Typography variant="subtitle2">{template.key}</Typography>
                                        <TextField
                                            label="Name"
                                            value={draft.name}
                                            onChange={(event) =>
                                                setTemplateDrafts((current) => ({
                                                    ...current,
                                                    [template.id]: { ...draft, name: event.target.value },
                                                }))
                                            }
                                            fullWidth
                                        />
                                        <TextField
                                            label="Subject"
                                            value={draft.subject_template}
                                            onChange={(event) =>
                                                setTemplateDrafts((current) => ({
                                                    ...current,
                                                    [template.id]: { ...draft, subject_template: event.target.value },
                                                }))
                                            }
                                            fullWidth
                                        />
                                        <TextField
                                            label="HTML body"
                                            value={draft.html_template}
                                            onChange={(event) =>
                                                setTemplateDrafts((current) => ({
                                                    ...current,
                                                    [template.id]: { ...draft, html_template: event.target.value },
                                                }))
                                            }
                                            fullWidth
                                            multiline
                                            minRows={4}
                                        />
                                        <TextField
                                            label="Text body"
                                            value={draft.text_template}
                                            onChange={(event) =>
                                                setTemplateDrafts((current) => ({
                                                    ...current,
                                                    [template.id]: { ...draft, text_template: event.target.value },
                                                }))
                                            }
                                            fullWidth
                                            multiline
                                            minRows={3}
                                        />
                                        <FormControlLabel
                                            control={
                                                <Switch
                                                    checked={draft.is_active}
                                                    onChange={(event) =>
                                                        setTemplateDrafts((current) => ({
                                                            ...current,
                                                            [template.id]: { ...draft, is_active: event.target.checked },
                                                        }))
                                                    }
                                                />
                                            }
                                            label="Active"
                                        />
                                        <Button
                                            variant="outlined"
                                            disabled={isSavingThisTemplate}
                                            onClick={() => updateTemplateMutation.mutate({ id: template.id, draft })}
                                        >
                                            {isSavingThisTemplate ? "Saving..." : "Save template"}
                                        </Button>
                                    </Stack>
                                </Box>
                            );
                        })}
                    </Stack>
                </Stack>
            </SectionCard>
        </PageShell>
    );
}

export default function AdminPlatformPage() {
    const { data: configData, isLoading: configLoading } = useQuery({
        queryKey: ["platform", "admin", "config"],
        queryFn: getPlatformConfig,
    });
    const { data: plans, isLoading: plansLoading } = useQuery({
        queryKey: ["platform", "admin", "plans"],
        queryFn: listAdminPlans,
    });
    const { data: flags, isLoading: flagsLoading } = useQuery({
        queryKey: ["platform", "admin", "feature-flags"],
        queryFn: listAdminFeatureFlags,
    });
    const { data: templates, isLoading: templatesLoading } = useQuery({
        queryKey: ["platform", "admin", "email-templates"],
        queryFn: listAdminEmailTemplates,
    });

    if (configLoading || plansLoading || flagsLoading || templatesLoading) {
        return (
            <PageShell maxWidth="xl">
                <Stack spacing={2}>
                    <Skeleton variant="rounded" height={180} sx={{ borderRadius: 6 }} />
                    <Skeleton variant="rounded" height={240} sx={{ borderRadius: 6 }} />
                    <Skeleton variant="rounded" height={240} sx={{ borderRadius: 6 }} />
                </Stack>
            </PageShell>
        );
    }

    if (!configData || !plans || !flags || !templates) {
        return null;
    }

    const pageKey = [
        configData.app_name,
        configData.module_pack,
        configData.module_catalog.map((item) => `${item.key}:${item.enabled}`).join("|"),
        plans.map((plan) => `${plan.id}:${plan.updated_at}`).join("|"),
        flags.map((flag) => `${flag.id}:${flag.updated_at}`).join("|"),
        templates.map((template) => `${template.id}:${template.updated_at}`).join("|"),
    ].join("::");

    return (
        <AdminPlatformContent
            key={pageKey}
            configData={configData}
            plans={plans}
            flags={flags}
            templates={templates}
        />
    );
}
