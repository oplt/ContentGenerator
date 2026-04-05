import { Box, Chip, Stack, Typography } from "@mui/material";
import { alpha } from "@mui/material/styles";

type PageHeaderProps = {
    eyebrow?: string;
    title: React.ReactNode;
    description?: React.ReactNode;
    actions?: React.ReactNode;
    meta?: React.ReactNode;
};

export function PageHeader({ eyebrow, title, description, actions, meta }: PageHeaderProps) {
    return (
        <Box
            sx={(theme) => ({
                position: "relative",
                overflow: "hidden",
                borderRadius: { xs: 4, md: 5 },
                border: `1px solid ${theme.palette.divider}`,
                px: { xs: 2.5, md: 4 },
                py: { xs: 3, md: 4 },
                background: `linear-gradient(180deg, ${alpha(theme.palette.background.paper, 0.96)} 0%, ${alpha(
                    theme.palette.background.paper,
                    0.88
                )} 100%)`,
                boxShadow:
                    theme.palette.mode === "dark"
                        ? "0 24px 60px rgba(2, 6, 23, 0.42)"
                        : "0 22px 46px rgba(15, 23, 42, 0.08)",
                "&::before": {
                    content: '""',
                    position: "absolute",
                    inset: "auto auto -20% -8%",
                    width: 240,
                    height: 240,
                    borderRadius: "50%",
                    background: alpha(theme.palette.primary.main, 0.12),
                    filter: "blur(8px)",
                },
                "&::after": {
                    content: '""',
                    position: "absolute",
                    inset: "-10% -6% auto auto",
                    width: 200,
                    height: 200,
                    borderRadius: "50%",
                    background: alpha(theme.palette.secondary.main, 0.1),
                    filter: "blur(10px)",
                },
            })}
        >
            <Stack
                direction={{ xs: "column", lg: actions ? "row" : "column" }}
                justifyContent="space-between"
                alignItems={{ xs: "flex-start", lg: "flex-end" }}
                spacing={3}
                sx={{ position: "relative", zIndex: 1 }}
            >
                <Box sx={{ maxWidth: 760 }}>
                    {eyebrow && (
                        <Chip
                            label={eyebrow}
                            size="small"
                            color="primary"
                            variant="outlined"
                            sx={{ mb: 1.5 }}
                        />
                    )}
                    <Typography variant="h3">{title}</Typography>
                    {description && (
                        <Typography
                            color="text.secondary"
                            sx={{ mt: 1.25, maxWidth: 720, fontSize: { xs: "0.95rem", md: "1.02rem" } }}
                        >
                            {description}
                        </Typography>
                    )}
                    {meta && (
                        <Stack direction="row" flexWrap="wrap" gap={1.25} sx={{ mt: 2.5 }}>
                            {meta}
                        </Stack>
                    )}
                </Box>
                {actions && (
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25} sx={{ width: { xs: "100%", lg: "auto" } }}>
                        {actions}
                    </Stack>
                )}
            </Stack>
        </Box>
    );
}
