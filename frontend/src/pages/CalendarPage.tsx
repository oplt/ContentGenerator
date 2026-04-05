import { useQuery } from "@tanstack/react-query";
import { Button, Chip } from "@mui/material";
import { ArrowForward as ArrowForwardIcon } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { listProjects } from "../api/projects";
import { DashboardCalendar } from "../components/dashboard/DashboardCalendar";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { usePlatformMetadata } from "../hooks/usePlatformMetadata";

export default function CalendarPage() {
    const navigate = useNavigate();
    const { data: platformMetadata } = usePlatformMetadata();
    const { data: projects, isLoading: projectsLoading } = useQuery({
        queryKey: ["projects"],
        queryFn: listProjects,
    });

    const coreDomainPlural = platformMetadata?.core_domain_plural ?? "Projects";

    return (
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Planning horizon"
                title="Calendar"
                description={`Plan events, appointments, and due work across your ${coreDomainPlural.toLowerCase()} from a dedicated scheduling view.`}
                actions={
                    <Button
                        variant="outlined"
                        endIcon={<ArrowForwardIcon />}
                        onClick={() => navigate("/projects")}
                    >
                        Open {coreDomainPlural}
                    </Button>
                }
                meta={
                    <Chip
                        label={`${projects?.length ?? 0} ${coreDomainPlural.toLowerCase()}`}
                        variant="outlined"
                    />
                }
            />

            <DashboardCalendar
                projects={projects ?? []}
                projectsLoading={projectsLoading}
                onOpenProjects={() => navigate("/projects")}
                allowedViews={["day", "week", "month", "twelve_month"]}
                initialView="month"
            />
        </PageShell>
    );
}
