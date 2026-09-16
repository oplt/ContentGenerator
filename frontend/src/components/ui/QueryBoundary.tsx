/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";

type EmptyConfig<T> = {
  when: (data: T) => boolean;
  title: string;
  description: string;
  action?: ReactNode;
};

/**
 * Truthful async boundary: loading only while pending without data;
 * errors never collapse into an indefinite spinner.
 */
export function QueryBoundary<T>({
  query,
  loadingLabel = "Loading",
  errorTitle,
  errorMessage = "This data could not be loaded.",
  empty,
  children,
  staleHint,
}: {
  query: Pick<UseQueryResult<T>, "data" | "isPending" | "isError" | "isFetching" | "refetch">;
  loadingLabel?: string;
  errorTitle?: string;
  errorMessage?: string;
  empty?: EmptyConfig<T>;
  children: (data: T) => ReactNode;
  staleHint?: ReactNode;
}) {
  if (query.isPending && query.data === undefined) {
    return <LoadingState label={loadingLabel} />;
  }

  if (query.isError && query.data === undefined) {
    return (
      <ErrorState
        title={errorTitle}
        message={errorMessage}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }

  if (query.data === undefined) {
    return (
      <ErrorState
        title={errorTitle}
        message={errorMessage}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }

  if (empty?.when(query.data)) {
    return (
      <EmptyState title={empty.title} description={empty.description} action={empty.action} />
    );
  }

  return (
    <>
      {staleHint && query.isFetching ? staleHint : null}
      {children(query.data)}
    </>
  );
}

/** Combine several queries into a single loading/error gate for page shells. */
export function resolveQueriesStatus(
  queries: Array<Pick<UseQueryResult<unknown>, "isPending" | "isError" | "data" | "refetch">>
):
  | { status: "loading" }
  | { status: "error"; retry: () => void }
  | { status: "ready" } {
  const pendingWithoutData = queries.some((q) => q.isPending && q.data === undefined);
  if (pendingWithoutData) {
    return { status: "loading" };
  }
  const failed = queries.filter((q) => q.isError && q.data === undefined);
  if (failed.length > 0) {
    return {
      status: "error",
      retry: () => {
        for (const q of failed) {
          void q.refetch();
        }
      },
    };
  }
  return { status: "ready" };
}
