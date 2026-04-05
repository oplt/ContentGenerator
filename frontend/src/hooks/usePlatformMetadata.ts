import { useQuery } from "@tanstack/react-query";

import { getPlatformMetadata } from "../api/platform";

export function usePlatformMetadata() {
    return useQuery({
        queryKey: ["platform", "metadata"],
        queryFn: getPlatformMetadata,
        staleTime: 5 * 60_000,
    });
}
