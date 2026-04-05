import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Avatar,
    Box,
    Button,
    Chip,
    CircularProgress,
    Link,
    Skeleton,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    DeleteOutline as DeleteIcon,
    Devices as DevicesIcon,
    PlaceOutlined as PlaceOutlinedIcon,
    Public as PublicIcon,
    UploadFile as UploadFileIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import { changePassword, getMe, getSessions, revokeSession, updateMe } from "../api/users";
import { deleteAvatar, getProfile, updateProfile, uploadAvatar } from "../api/profile";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDate, formatDateTime, getInitials } from "../utils/formatters";

const accountSchema = z.object({
    full_name: z.string().optional(),
});

const profileSchema = z.object({
    bio: z.string().max(1000, "Bio is too long").nullable().optional(),
    location: z.string().max(255, "Location is too long").nullable().optional(),
    website: z.string().max(500, "Website is too long").nullable().optional(),
});

const passwordSchema = z
    .object({
        current_password: z.string().min(1, "Required"),
        new_password: z.string().min(8, "At least 8 characters"),
        confirm_password: z.string(),
    })
    .refine((data) => data.new_password === data.confirm_password, {
        message: "Passwords do not match",
        path: ["confirm_password"],
    });

type AccountValues = z.infer<typeof accountSchema>;
type ProfileValues = z.infer<typeof profileSchema>;
type PasswordValues = z.infer<typeof passwordSchema>;

export default function ProfilePage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const { data: user, isLoading: userLoading } = useQuery({
        queryKey: ["me"],
        queryFn: getMe,
    });
    const { data: profile, isLoading: profileLoading } = useQuery({
        queryKey: ["profile"],
        queryFn: getProfile,
    });
    const { data: sessions, isLoading: sessionsLoading } = useQuery({
        queryKey: ["sessions"],
        queryFn: getSessions,
    });

    const accountForm = useForm<AccountValues>({
        resolver: zodResolver(accountSchema),
        values: { full_name: user?.full_name ?? "" },
    });
    const profileForm = useForm<ProfileValues>({
        resolver: zodResolver(profileSchema),
        values: {
            bio: profile?.bio ?? "",
            location: profile?.location ?? "",
            website: profile?.website ?? "",
        },
    });
    const passwordForm = useForm<PasswordValues>({
        resolver: zodResolver(passwordSchema),
    });

    const accountMutation = useMutation({
        mutationFn: updateMe,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["me"] }),
    });
    const profileMutation = useMutation({
        mutationFn: updateProfile,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["profile"] }),
    });
    const passwordMutation = useMutation({
        mutationFn: changePassword,
        onSuccess: () => passwordForm.reset(),
    });
    const revokeSessionMutation = useMutation({
        mutationFn: revokeSession,
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sessions"] }),
    });
    const uploadAvatarMutation = useMutation({
        mutationFn: uploadAvatar,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["profile"] });
            showToast({ message: "Avatar updated.", severity: "success" });
        },
        onError: (error) => {
            showToast({
                message: error instanceof Error ? error.message : "Failed to upload avatar.",
                severity: "error",
            });
        },
    });
    const deleteAvatarMutation = useMutation({
        mutationFn: deleteAvatar,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["profile"] });
            showToast({ message: "Avatar removed.", severity: "success" });
        },
        onError: (error) => {
            showToast({
                message: error instanceof Error ? error.message : "Failed to remove avatar.",
                severity: "error",
            });
        },
    });

    function handleAvatarFileChange(file: File | null) {
        if (!file) {
            return;
        }
        uploadAvatarMutation.mutate(file);
    }

    if (userLoading || profileLoading) {
        return (
            <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
                <CircularProgress />
            </Box>
        );
    }

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Personal settings"
                title="Profile"
                description="Manage identity, public details, active sessions, and password security from a single polished account hub."
                meta={
                    <>
                        <Chip
                            label={user?.is_verified ? "Email verified" : "Email verification needed"}
                            color={user?.is_verified ? "success" : "warning"}
                            variant="outlined"
                        />
                        <Chip
                            label={user?.mfa_enabled ? "MFA enabled" : "MFA recommended"}
                            color={user?.mfa_enabled ? "success" : "default"}
                            variant="outlined"
                        />
                    </>
                }
            />

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", lg: "minmax(320px, 0.92fr) minmax(0, 1.08fr)" },
                    alignItems: "start",
                }}
            >
                <SectionCard>
                    <Stack spacing={2.5}>
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={2.5} alignItems={{ xs: "flex-start", sm: "center" }}>
                            <Avatar
                                src={profile?.avatar_url ?? undefined}
                                sx={{ width: 88, height: 88, fontSize: 28 }}
                            >
                                {getInitials(user?.full_name, user?.email)}
                            </Avatar>
                            <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                                <Typography variant="h5">{user?.full_name ?? "Your profile"}</Typography>
                                <Typography color="text.secondary">{user?.email}</Typography>
                                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                                    Upload JPG, PNG, GIF, or WebP up to 5 MB for a sharper account presence.
                                </Typography>
                            </Box>
                        </Stack>

                        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25}>
                            <Button
                                component="label"
                                variant="contained"
                                startIcon={<UploadFileIcon />}
                                disabled={uploadAvatarMutation.isPending}
                            >
                                {uploadAvatarMutation.isPending ? "Uploading..." : "Upload avatar"}
                                <input
                                    hidden
                                    accept="image/*"
                                    type="file"
                                    onChange={(event) => {
                                        handleAvatarFileChange(event.target.files?.[0] ?? null);
                                        event.currentTarget.value = "";
                                    }}
                                />
                            </Button>
                            <Button
                                variant="outlined"
                                color="error"
                                startIcon={<DeleteIcon />}
                                disabled={!profile?.avatar_url || deleteAvatarMutation.isPending}
                                onClick={() => deleteAvatarMutation.mutate()}
                            >
                                {deleteAvatarMutation.isPending ? "Removing..." : "Remove avatar"}
                            </Button>
                        </Stack>

                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.25,
                                gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
                            }}
                        >
                            <Box
                                sx={(theme) => ({
                                    p: 2,
                                    borderRadius: 4,
                                    border: `1px solid ${theme.palette.divider}`,
                                    backgroundColor: alpha(theme.palette.background.paper, 0.78),
                                })}
                            >
                                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
                                    <PlaceOutlinedIcon fontSize="small" color="action" />
                                    <Typography variant="subtitle2">Location</Typography>
                                </Stack>
                                <Typography variant="body2" color="text.secondary">
                                    {profile?.location || "No location set"}
                                </Typography>
                            </Box>
                            <Box
                                sx={(theme) => ({
                                    p: 2,
                                    borderRadius: 4,
                                    border: `1px solid ${theme.palette.divider}`,
                                    backgroundColor: alpha(theme.palette.background.paper, 0.78),
                                })}
                            >
                                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
                                    <PublicIcon fontSize="small" color="action" />
                                    <Typography variant="subtitle2">Website</Typography>
                                </Stack>
                                {profile?.website ? (
                                    <Link href={profile.website} target="_blank" rel="noreferrer" underline="hover">
                                        {profile.website}
                                    </Link>
                                ) : (
                                    <Typography variant="body2" color="text.secondary">
                                        No website shared
                                    </Typography>
                                )}
                            </Box>
                        </Box>
                    </Stack>
                </SectionCard>

                <SectionCard title="Account info" description="Update how your name appears across the product.">
                    <Box component="form" onSubmit={accountForm.handleSubmit((values) => accountMutation.mutate(values))}>
                        <Stack spacing={2}>
                            <TextField
                                label="Full name"
                                {...accountForm.register("full_name")}
                                error={!!accountForm.formState.errors.full_name}
                                helperText={accountForm.formState.errors.full_name?.message}
                                fullWidth
                            />
                            {accountMutation.isSuccess && <Alert severity="success">Account details updated.</Alert>}
                            {accountMutation.isError && (
                                <Alert severity="error">
                                    {accountMutation.error instanceof Error
                                        ? accountMutation.error.message
                                        : "Failed to update account info."}
                                </Alert>
                            )}
                            <Button type="submit" variant="contained" disabled={accountMutation.isPending}>
                                {accountMutation.isPending ? "Saving..." : "Save changes"}
                            </Button>
                        </Stack>
                    </Box>
                </SectionCard>
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gap: 2,
                    gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.05fr) minmax(320px, 0.95fr)" },
                    alignItems: "start",
                }}
            >
                <SectionCard title="Public profile" description="Control the profile details other users can discover.">
                    <Box
                        component="form"
                        onSubmit={profileForm.handleSubmit((values) =>
                            profileMutation.mutate({
                                bio: values.bio || null,
                                location: values.location || null,
                                website: values.website || null,
                            })
                        )}
                    >
                        <Stack spacing={2}>
                            <TextField
                                label="Bio"
                                {...profileForm.register("bio")}
                                error={!!profileForm.formState.errors.bio}
                                helperText={profileForm.formState.errors.bio?.message}
                                multiline
                                minRows={5}
                                fullWidth
                            />
                            <TextField
                                label="Location"
                                {...profileForm.register("location")}
                                error={!!profileForm.formState.errors.location}
                                helperText={profileForm.formState.errors.location?.message}
                                fullWidth
                            />
                            <TextField
                                label="Website"
                                {...profileForm.register("website")}
                                error={!!profileForm.formState.errors.website}
                                helperText={profileForm.formState.errors.website?.message}
                                fullWidth
                            />
                            {profileMutation.isSuccess && <Alert severity="success">Public profile updated.</Alert>}
                            {profileMutation.isError && (
                                <Alert severity="error">
                                    {profileMutation.error instanceof Error
                                        ? profileMutation.error.message
                                        : "Failed to update public profile."}
                                </Alert>
                            )}
                            <Button type="submit" variant="contained" disabled={profileMutation.isPending}>
                                {profileMutation.isPending ? "Saving..." : "Save public profile"}
                            </Button>
                        </Stack>
                    </Box>
                </SectionCard>

                <Stack spacing={2}>
                    <SectionCard title="Active sessions" description="Review and revoke sessions you no longer trust.">
                        {sessionsLoading ? (
                            <Stack spacing={1.25}>
                                {Array.from({ length: 3 }).map((_, index) => (
                                    <Skeleton key={index} variant="rounded" height={84} sx={{ borderRadius: 4 }} />
                                ))}
                            </Stack>
                        ) : sessions && sessions.length > 0 ? (
                            <Stack spacing={1.25}>
                                {sessions.map((session, index) => {
                                    const isRevokingThisItem =
                                        revokeSessionMutation.isPending &&
                                        revokeSessionMutation.variables === session.id;
                                    return (
                                        <Box
                                            key={session.id}
                                            sx={(theme) => ({
                                                p: 2,
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
                                                    <Typography variant="subtitle2">{`Session ${index + 1}`}</Typography>
                                                    <Typography variant="body2" color="text.secondary">
                                                        Started {formatDateTime(session.created_at)}
                                                    </Typography>
                                                    <Typography variant="caption" color="text.secondary">
                                                        Expires {formatDate(session.expires_at)}
                                                    </Typography>
                                                </Box>
                                                <Box>
                                                    <Button
                                                        variant="outlined"
                                                        color="error"
                                                        size="small"
                                                        disabled={isRevokingThisItem}
                                                        onClick={() => revokeSessionMutation.mutate(session.id)}
                                                    >
                                                        {isRevokingThisItem ? "Revoking..." : "Revoke"}
                                                    </Button>
                                                </Box>
                                            </Stack>
                                        </Box>
                                    );
                                })}
                            </Stack>
                        ) : (
                            <EmptyState
                                icon={<DevicesIcon />}
                                title="No active sessions"
                                description="Your signed-in sessions will appear here when they are available."
                            />
                        )}
                    </SectionCard>

                    <SectionCard title="Change password" description="Refresh your credentials to keep account access secure.">
                        <Box
                            component="form"
                            onSubmit={passwordForm.handleSubmit((values) =>
                                passwordMutation.mutate({
                                    current_password: values.current_password,
                                    new_password: values.new_password,
                                })
                            )}
                        >
                            <Stack spacing={2}>
                                <TextField
                                    label="Current password"
                                    type="password"
                                    {...passwordForm.register("current_password")}
                                    error={!!passwordForm.formState.errors.current_password}
                                    helperText={passwordForm.formState.errors.current_password?.message}
                                    fullWidth
                                />
                                <TextField
                                    label="New password"
                                    type="password"
                                    {...passwordForm.register("new_password")}
                                    error={!!passwordForm.formState.errors.new_password}
                                    helperText={passwordForm.formState.errors.new_password?.message}
                                    fullWidth
                                />
                                <TextField
                                    label="Confirm new password"
                                    type="password"
                                    {...passwordForm.register("confirm_password")}
                                    error={!!passwordForm.formState.errors.confirm_password}
                                    helperText={passwordForm.formState.errors.confirm_password?.message}
                                    fullWidth
                                />
                                {passwordMutation.isSuccess && <Alert severity="success">Password updated.</Alert>}
                                {passwordMutation.isError && (
                                    <Alert severity="error">
                                        {passwordMutation.error instanceof Error
                                            ? passwordMutation.error.message
                                            : "Failed to update password."}
                                    </Alert>
                                )}
                                <Button type="submit" variant="contained" disabled={passwordMutation.isPending}>
                                    {passwordMutation.isPending ? "Updating..." : "Update password"}
                                </Button>
                            </Stack>
                        </Box>
                    </SectionCard>
                </Stack>
            </Box>
        </PageShell>
    );
}
