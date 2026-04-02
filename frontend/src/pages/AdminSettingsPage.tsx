import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    IconButton,
    Skeleton,
    Stack,
    Tab,
    Tabs,
    TextField,
    Typography,
} from "@mui/material";
import {
    DeleteOutline as DeleteIcon,
    RestartAlt as RestartIcon,
    SettingsSuggest as SettingsIcon,
    Storage as StorageIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import {
    createDatabaseSetting,
    deleteDatabaseSetting,
    getConfigSettings,
    listDatabaseSettings,
    updateConfigSettings,
    updateDatabaseSetting,
    type ConfigEntry,
    type ConfigSettingsResponse,
    type DatabaseSetting,
} from "../api/settings";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { StatCard } from "../components/ui/StatCard";
import { formatDateTime } from "../utils/formatters";

type DatabaseSettingDrafts = Record<
    string,
    {
        value: string;
        description: string;
    }
>;

type ConfigGroupId =
    | "application"
    | "infrastructure"
    | "security"
    | "email"
    | "observability"
    | "storage"
    | "custom";

type SettingsTabValue = ConfigGroupId | "database";

type ConfigGroupDefinition = {
    id: ConfigGroupId;
    label: string;
    description: string;
};

const CONFIG_GROUP_DEFINITIONS: ConfigGroupDefinition[] = [
    {
        id: "application",
        label: "Application",
        description: "Branding, naming, environment identity, and app-facing defaults.",
    },
    {
        id: "infrastructure",
        label: "Infrastructure",
        description: "Hosts, ports, databases, cache, and background job plumbing.",
    },
    {
        id: "security",
        label: "Auth & Security",
        description: "Token behavior, cookies, verification windows, and admin access controls.",
    },
    {
        id: "email",
        label: "Email",
        description: "SMTP delivery settings for verification, reset, and notification mail.",
    },
    {
        id: "observability",
        label: "Observability",
        description: "Tracing, error capture, and telemetry export configuration.",
    },
    {
        id: "storage",
        label: "Storage",
        description: "Object storage connectivity, URL generation, and avatar upload limits.",
    },
    {
        id: "custom",
        label: "Custom",
        description: "Unmapped or custom environment variables kept in `backend/.env`.",
    },
];

function getConfigGroupId(item: ConfigEntry): ConfigGroupId {
    const { key, is_custom } = item;

    if (is_custom) {
        return "custom";
    }
    if (
        key.startsWith("APP_") ||
        key === "LOG_LEVEL" ||
        key.startsWith("CORE_DOMAIN_") ||
        key === "PLATFORM_DEFAULT_MODULE_PACK" ||
        key === "FRONTEND_URL"
    ) {
        return "application";
    }
    if (
        key === "DATABASE_URL" ||
        key === "REDIS_URL" ||
        key.startsWith("CELERY_")
    ) {
        return "infrastructure";
    }
    if (
        key.startsWith("JWT_") ||
        key === "ACCESS_TOKEN_EXPIRE_MINUTES" ||
        key === "REFRESH_TOKEN_EXPIRE_DAYS" ||
        key === "COOKIE_SECURE" ||
        key === "VERIFICATION_TOKEN_TTL" ||
        key === "PASSWORD_RESET_TOKEN_TTL" ||
        key === "ADMIN_SIGNUP_INVITE_CODE"
    ) {
        return "security";
    }
    if (key.startsWith("SMTP_")) {
        return "email";
    }
    if (key.startsWith("SENTRY_") || key.startsWith("OTLP_")) {
        return "observability";
    }
    if (key.startsWith("STORAGE_")) {
        return "storage";
    }

    return "custom";
}

function buildConfigGroups(items: ConfigEntry[]) {
    const grouped = Object.fromEntries(
        CONFIG_GROUP_DEFINITIONS.map((group) => [group.id, [] as ConfigEntry[]])
    ) as Record<ConfigGroupId, ConfigEntry[]>;

    items.forEach((item) => {
        grouped[getConfigGroupId(item)].push(item);
    });

    return CONFIG_GROUP_DEFINITIONS
        .map((group) => ({
            ...group,
            items: grouped[group.id],
        }))
        .filter((group) => group.items.length > 0);
}

function ConfigEntryEditor({
    item,
    value,
    onChange,
}: {
    item: ConfigEntry;
    value: string;
    onChange: (nextValue: string) => void;
}) {
    return (
        <Box
            sx={(theme) => ({
                p: 2,
                borderRadius: 4,
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: alpha(theme.palette.background.paper, 0.78),
            })}
        >
            <Stack spacing={1.25}>
                <Stack
                    direction={{ xs: "column", sm: "row" }}
                    justifyContent="space-between"
                    spacing={1}
                >
                    <Box>
                        <Typography variant="subtitle2">{item.key}</Typography>
                        {item.description && (
                            <Typography variant="body2" color="text.secondary">
                                {item.description}
                            </Typography>
                        )}
                    </Box>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip label={item.value_type} size="small" variant="outlined" />
                        {item.is_custom && <Chip label="custom" size="small" variant="outlined" />}
                        {item.requires_restart && (
                            <Chip
                                label="restart recommended"
                                size="small"
                                color="warning"
                                variant="outlined"
                            />
                        )}
                    </Stack>
                </Stack>
                <TextField value={value} onChange={(event) => onChange(event.target.value)} fullWidth />
            </Stack>
        </Box>
    );
}

function DatabaseSettingEditor({
    item,
    draft,
    onDraftChange,
    onSave,
    onDelete,
    isSaving,
    isDeleting,
}: {
    item: DatabaseSetting;
    draft: {
        value: string;
        description: string;
    };
    onDraftChange: (nextDraft: { value: string; description: string }) => void;
    onSave: () => void;
    onDelete: () => void;
    isSaving: boolean;
    isDeleting: boolean;
}) {
    return (
        <Box
            sx={(theme) => ({
                p: 2.25,
                borderRadius: 4,
                border: `1px solid ${theme.palette.divider}`,
            })}
        >
            <Stack spacing={1.5}>
                <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                    <Box>
                        <Typography variant="subtitle2">{item.key}</Typography>
                        <Typography variant="caption" color="text.secondary">
                            Updated {formatDateTime(item.updated_at)}
                        </Typography>
                    </Box>
                    <IconButton color="error" onClick={onDelete} disabled={isDeleting}>
                        <DeleteIcon />
                    </IconButton>
                </Stack>
                <TextField
                    label="Value"
                    value={draft.value}
                    onChange={(event) =>
                        onDraftChange({
                            value: event.target.value,
                            description: draft.description,
                        })
                    }
                    fullWidth
                    multiline
                    minRows={3}
                />
                <TextField
                    label="Description"
                    value={draft.description}
                    onChange={(event) =>
                        onDraftChange({
                            value: draft.value,
                            description: event.target.value,
                        })
                    }
                    fullWidth
                    multiline
                    minRows={3}
                />
                <Button variant="contained" disabled={isSaving} onClick={onSave}>
                    {isSaving ? "Saving..." : "Save setting"}
                </Button>
            </Stack>
        </Box>
    );
}

function AdminSettingsContent({
    configData,
    databaseSettings,
    configErrorMessage,
    databaseErrorMessage,
    hasConfigError,
    hasDatabaseError,
    activeTab,
    onTabChange,
}: {
    configData: ConfigSettingsResponse;
    databaseSettings: DatabaseSetting[];
    configErrorMessage: string;
    databaseErrorMessage: string;
    hasConfigError: boolean;
    hasDatabaseError: boolean;
    activeTab: SettingsTabValue;
    onTabChange: (nextTab: SettingsTabValue) => void;
}) {
    const queryClient = useQueryClient();
    const configGroups = buildConfigGroups(configData.items);
    const [configDrafts, setConfigDrafts] = useState<Record<string, string>>(() =>
        Object.fromEntries(configData.items.map((item) => [item.key, item.value]))
    );
    const [databaseDrafts, setDatabaseDrafts] = useState<DatabaseSettingDrafts>(() =>
        Object.fromEntries(
            databaseSettings.map((item) => [
                item.id,
                {
                    value: item.value,
                    description: item.description ?? "",
                },
            ])
        )
    );
    const [newSetting, setNewSetting] = useState({
        key: "",
        value: "",
        description: "",
    });

    const activeConfigGroup =
        activeTab === "database"
            ? null
            : configGroups.find((group) => group.id === activeTab) ?? configGroups[0] ?? null;
    const restartSensitiveCount = configData.items.filter((item) => item.requires_restart).length;
    const customConfigCount = configData.items.filter((item) => item.is_custom).length;
    const changedConfigCount = configData.items.filter(
        (item) => (configDrafts[item.key] ?? item.value) !== item.value
    ).length;

    const configMutation = useMutation({
        mutationFn: updateConfigSettings,
        onSuccess: (data) => {
            queryClient.setQueryData(["settings", "config"], data);
            setConfigDrafts(Object.fromEntries(data.items.map((item) => [item.key, item.value])));
        },
    });
    const createDatabaseMutation = useMutation({
        mutationFn: createDatabaseSetting,
        onSuccess: async () => {
            setNewSetting({ key: "", value: "", description: "" });
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });
    const updateDatabaseMutation = useMutation({
        mutationFn: ({ id, value, description }: { id: string; value: string; description: string }) =>
            updateDatabaseSetting(id, { value, description }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });
    const deleteDatabaseMutation = useMutation({
        mutationFn: deleteDatabaseSetting,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["settings", "database"] });
        },
    });

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="System control"
                title="Settings"
                description="Edit environment-backed variables in grouped tabs and keep runtime database settings separate from file-based config."
                meta={
                    <>
                        <Chip label={`${configGroups.length} config groups`} variant="outlined" />
                        <Chip label={`${customConfigCount} custom values`} variant="outlined" />
                        <Chip label={`${databaseSettings.length} database settings`} variant="outlined" />
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
                        xl: "repeat(3, minmax(0, 1fr))",
                    },
                }}
            >
                <StatCard
                    label="Config variables"
                    value={configData.items.length}
                    description="Environment-backed values available in the settings file"
                    icon={<SettingsIcon />}
                />
                <StatCard
                    label="Restart-sensitive"
                    value={restartSensitiveCount}
                    description="Values likely to require a backend restart after saving"
                    icon={<RestartIcon />}
                    color="warning"
                />
                <StatCard
                    label="Runtime database settings"
                    value={databaseSettings.length}
                    description="Key/value records stored in the database for live updates"
                    icon={<StorageIcon />}
                    color="secondary"
                />
            </Box>

            {hasConfigError && <Alert severity="error">{configErrorMessage}</Alert>}
            {hasDatabaseError && <Alert severity="error">{databaseErrorMessage}</Alert>}

            <Box
                sx={(theme) => ({
                    p: 1,
                    borderRadius: 4,
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: alpha(theme.palette.background.paper, 0.82),
                })}
            >
                <Tabs
                    value={activeTab}
                    onChange={(_, value: SettingsTabValue) => onTabChange(value)}
                    variant="scrollable"
                    scrollButtons="auto"
                    allowScrollButtonsMobile
                >
                    {configGroups.map((group) => (
                        <Tab
                            key={group.id}
                            value={group.id}
                            label={`${group.label} (${group.items.length})`}
                        />
                    ))}
                    <Tab
                        value="database"
                        label={`Database settings (${databaseSettings.length})`}
                    />
                </Tabs>
            </Box>

            {activeConfigGroup ? (
                <SectionCard
                    title={activeConfigGroup.label}
                    description={activeConfigGroup.description}
                    action={
                        <Button
                            variant="contained"
                            disabled={configMutation.isPending || changedConfigCount === 0}
                            onClick={() =>
                                configMutation.mutate({
                                    items: configData.items.map((item) => ({
                                        key: item.key,
                                        value: configDrafts[item.key] ?? "",
                                    })),
                                })
                            }
                        >
                            {configMutation.isPending ? "Saving..." : "Save all config"}
                        </Button>
                    }
                >
                    <Stack spacing={2}>
                        <Alert severity="info">{configData.notice}</Alert>
                        {configMutation.isSuccess && (
                            <Alert severity="success">
                                Config saved. Restart the backend if a startup-bound value changed.
                            </Alert>
                        )}
                        {configMutation.isError && (
                            <Alert severity="error">
                                {configMutation.error instanceof Error
                                    ? configMutation.error.message
                                    : "Failed to save config."}
                            </Alert>
                        )}

                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Chip
                                label={`${activeConfigGroup.items.length} variables in this group`}
                                variant="outlined"
                            />
                            <Chip
                                label={
                                    changedConfigCount > 0
                                        ? `${changedConfigCount} unsaved changes across all tabs`
                                        : "No unsaved config changes"
                                }
                                color={changedConfigCount > 0 ? "warning" : "default"}
                                variant="outlined"
                            />
                        </Stack>

                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" },
                                alignItems: "start",
                            }}
                        >
                            {activeConfigGroup.items.map((item) => (
                                <ConfigEntryEditor
                                    key={item.key}
                                    item={item}
                                    value={configDrafts[item.key] ?? item.value}
                                    onChange={(nextValue) =>
                                        setConfigDrafts((current) => ({
                                            ...current,
                                            [item.key]: nextValue,
                                        }))
                                    }
                                />
                            ))}
                        </Box>
                    </Stack>
                </SectionCard>
            ) : (
                <Box
                    sx={{
                        display: "grid",
                        gap: 2,
                        gridTemplateColumns: { xs: "1fr", lg: "minmax(320px, 0.9fr) minmax(0, 1.1fr)" },
                        alignItems: "start",
                    }}
                >
                    <SectionCard
                        title="Add database setting"
                        description="Store arbitrary key/value settings inside the database."
                    >
                        <Stack spacing={2}>
                            {createDatabaseMutation.isSuccess && (
                                <Alert severity="success">Database setting created.</Alert>
                            )}
                            {createDatabaseMutation.isError && (
                                <Alert severity="error">
                                    {createDatabaseMutation.error instanceof Error
                                        ? createDatabaseMutation.error.message
                                        : "Failed to create database setting."}
                                </Alert>
                            )}
                            <TextField
                                label="Key"
                                value={newSetting.key}
                                onChange={(event) =>
                                    setNewSetting((current) => ({
                                        ...current,
                                        key: event.target.value,
                                    }))
                                }
                                fullWidth
                            />
                            <TextField
                                label="Value"
                                value={newSetting.value}
                                onChange={(event) =>
                                    setNewSetting((current) => ({
                                        ...current,
                                        value: event.target.value,
                                    }))
                                }
                                fullWidth
                                multiline
                                minRows={3}
                            />
                            <TextField
                                label="Description"
                                value={newSetting.description}
                                onChange={(event) =>
                                    setNewSetting((current) => ({
                                        ...current,
                                        description: event.target.value,
                                    }))
                                }
                                fullWidth
                                multiline
                                minRows={3}
                            />
                            <Button
                                variant="contained"
                                disabled={createDatabaseMutation.isPending || !newSetting.key.trim()}
                                onClick={() =>
                                    createDatabaseMutation.mutate({
                                        key: newSetting.key.trim(),
                                        value: newSetting.value,
                                        description: newSetting.description || undefined,
                                    })
                                }
                            >
                                {createDatabaseMutation.isPending ? "Adding..." : "Add setting"}
                            </Button>
                        </Stack>
                    </SectionCard>

                    <SectionCard
                        title="Database settings"
                        description="Review, edit, and delete runtime settings stored in the database."
                    >
                        {databaseSettings.length > 0 ? (
                            <Box
                                sx={{
                                    display: "grid",
                                    gap: 1.5,
                                    gridTemplateColumns: { xs: "1fr", xl: "repeat(2, minmax(0, 1fr))" },
                                    alignItems: "start",
                                }}
                            >
                                {databaseSettings.map((item) => {
                                    const isSavingThisItem =
                                        updateDatabaseMutation.isPending &&
                                        updateDatabaseMutation.variables?.id === item.id;
                                    const isDeletingThisItem =
                                        deleteDatabaseMutation.isPending &&
                                        deleteDatabaseMutation.variables === item.id;

                                    return (
                                        <DatabaseSettingEditor
                                            key={item.id}
                                            item={item}
                                            draft={databaseDrafts[item.id] ?? {
                                                value: item.value,
                                                description: item.description ?? "",
                                            }}
                                            onDraftChange={(nextDraft) =>
                                                setDatabaseDrafts((current) => ({
                                                    ...current,
                                                    [item.id]: nextDraft,
                                                }))
                                            }
                                            onSave={() =>
                                                updateDatabaseMutation.mutate({
                                                    id: item.id,
                                                    value: databaseDrafts[item.id]?.value ?? item.value,
                                                    description:
                                                        databaseDrafts[item.id]?.description ??
                                                        item.description ??
                                                        "",
                                                })
                                            }
                                            onDelete={() => deleteDatabaseMutation.mutate(item.id)}
                                            isSaving={isSavingThisItem}
                                            isDeleting={isDeletingThisItem}
                                        />
                                    );
                                })}
                            </Box>
                        ) : (
                            <EmptyState
                                icon={<StorageIcon />}
                                title="No database settings yet"
                                description="Create a setting when you need runtime-configurable values stored in the database."
                            />
                        )}
                    </SectionCard>
                </Box>
            )}
        </PageShell>
    );
}

export default function AdminSettingsPage() {
    const [activeTab, setActiveTab] = useState<SettingsTabValue>("application");
    const {
        data: configData,
        isLoading: configLoading,
        error: configError,
    } = useQuery({
        queryKey: ["settings", "config"],
        queryFn: getConfigSettings,
    });
    const {
        data: databaseSettings,
        isLoading: databaseLoading,
        error: databaseError,
    } = useQuery({
        queryKey: ["settings", "database"],
        queryFn: listDatabaseSettings,
    });

    if ((configLoading && !configData) || (databaseLoading && !databaseSettings)) {
        return (
            <PageShell maxWidth="xl">
                <Stack spacing={2}>
                    <Skeleton variant="rounded" height={180} sx={{ borderRadius: 6 }} />
                    <Skeleton variant="rounded" height={320} sx={{ borderRadius: 6 }} />
                </Stack>
            </PageShell>
        );
    }

    if (!configData || !databaseSettings) {
        return null;
    }

    const configGroups = buildConfigGroups(configData.items);
    const resolvedActiveTab =
        activeTab === "database" || configGroups.some((group) => group.id === activeTab)
            ? activeTab
            : configGroups[0]?.id ?? "database";
    const settingsKey = `${configData.items.map((item) => `${item.key}:${item.value}`).join("|")}::${databaseSettings
        .map((item) => `${item.id}:${item.updated_at}`)
        .join("|")}`;

    return (
        <AdminSettingsContent
            key={settingsKey}
            configData={configData}
            databaseSettings={databaseSettings}
            configErrorMessage={
                configError instanceof Error ? configError.message : "Failed to load config values."
            }
            databaseErrorMessage={
                databaseError instanceof Error ? databaseError.message : "Failed to load database settings."
            }
            hasConfigError={Boolean(configError)}
            hasDatabaseError={Boolean(databaseError)}
            activeTab={resolvedActiveTab}
            onTabChange={setActiveTab}
        />
    );
}
