"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import type { ServeInfoResponse } from "@/shared/types/api";
import { getRuntimeEnv } from "@/shared/lib/runtime-env";
import { Skeleton } from "@/shared/ui/skeleton";
import { LangPicker } from "./ui-primitives";

const CodeEditor = dynamic(() => import("@/shared/ui/code-editor").then((m) => m.CodeEditor), {
  ssr: false,
  loading: () => <Skeleton height={180} borderRadius={8} />,
});

export function ServeCodeSnippets({
  serveInfo,
  optimizationId,
  pairIndex,
}: {
  serveInfo: ServeInfoResponse;
  optimizationId: string;
  pairIndex?: number;
}) {
  const [codeTab, setCodeTab] = useState<"curl" | "python" | "javascript" | "go" | "dspy">("curl");
  const apiBase = getRuntimeEnv().apiUrl;
  const url =
    pairIndex != null
      ? `${apiBase}/serve/${optimizationId}/pair/${pairIndex}`
      : `${apiBase}/serve/${optimizationId}`;
  const artifactUrl = `${apiBase}/optimizations/${optimizationId}/artifact`;
  const gridResultUrl = `${apiBase}/optimizations/${optimizationId}/grid-result`;
  const model = serveInfo.model_name || "gpt-4o-mini";

  // Prefill real values the backend supplies (a demo example, or the first
  // dataset row when the optimizer ships no demos); placeholder the rest.
  const valueFor = (field: string): string => serveInfo.sample_inputs?.[field] ?? `<${field}>`;

  const inputsObj = serveInfo.input_fields
    .map((f) => `"${f}": ${JSON.stringify(valueFor(f))}`)
    .join(", ");
  const inputsJson = JSON.stringify({
    inputs: Object.fromEntries(serveInfo.input_fields.map((f) => [f, valueFor(f)])),
  });
  const tokenHint = `# Generate a token in Settings → API, then set it in your environment`;
  const snippets = {
    curl: [
      tokenHint,
      `#   export SKYNET_API_TOKEN=skyd_...`,
      `# Send a POST request to the optimized program endpoint`,
      `curl -X POST ${url} \\`,
      `  -H "Authorization: Bearer $SKYNET_API_TOKEN" \\`,
      `  -H "Content-Type: application/json" \\`,
      `  -d '${inputsJson}'`,
    ].join("\n"),
    python: [
      `import os`,
      `import requests`,
      ``,
      `# Generate a token in Settings → API and set SKYNET_API_TOKEN in your env`,
      `token = os.environ["SKYNET_API_TOKEN"]`,
      ``,
      `# Call the optimized program via the REST API`,
      `response = requests.post(`,
      `    "${url}",`,
      `    headers={"Authorization": f"Bearer {token}"},`,
      `    json={"inputs": {${inputsObj}}},`,
      `)`,
      ``,
      `# Parse and print the results`,
      `result = response.json()`,
      ...serveInfo.output_fields.map((f) => `print(result["outputs"]["${f}"])`),
    ].join("\n"),
    javascript: [
      `// Generate a token in Settings → API and set SKYNET_API_TOKEN in your env`,
      `const token = process.env.SKYNET_API_TOKEN;`,
      ``,
      `// Call the optimized program via fetch`,
      `const response = await fetch("${url}", {`,
      `  method: "POST",`,
      `  headers: {`,
      `    "Authorization": "Bearer " + token,`,
      `    "Content-Type": "application/json",`,
      `  },`,
      `  body: JSON.stringify({ inputs: { ${serveInfo.input_fields
        .map((f) => `${f}: ${JSON.stringify(valueFor(f))}`)
        .join(", ")} } }),`,
      `});`,
      ``,
      `// Parse and use the results`,
      `const result = await response.json();`,
      ...serveInfo.output_fields.map((f) => `console.log(result.outputs.${f});`),
    ].join("\n"),
    go: [
      `package main`,
      ``,
      `import (`,
      `\t"bytes"`,
      `\t"encoding/json"`,
      `\t"fmt"`,
      `\t"net/http"`,
      `\t"os"`,
      `)`,
      ``,
      `func main() {`,
      `\t// Generate a token in Settings → API and set SKYNET_API_TOKEN in your env`,
      `\ttoken := os.Getenv("SKYNET_API_TOKEN")`,
      ``,
      `\t// Build the request payload`,
      `\tpayload, _ := json.Marshal(map[string]any{`,
      `\t\t"inputs": map[string]string{`,
      ...serveInfo.input_fields.map((f) => `\t\t\t"${f}": ${JSON.stringify(valueFor(f))},`),
      `\t\t},`,
      `\t})`,
      ``,
      `\t// Send an authenticated POST request to the optimized program`,
      `\treq, _ := http.NewRequest("POST", "${url}", bytes.NewReader(payload))`,
      `\treq.Header.Set("Authorization", "Bearer "+token)`,
      `\treq.Header.Set("Content-Type", "application/json")`,
      `\tresp, _ := http.DefaultClient.Do(req)`,
      `\tdefer resp.Body.Close()`,
      ``,
      `\t// Decode the response`,
      `\tvar result map[string]any`,
      `\tjson.NewDecoder(resp.Body).Decode(&result)`,
      `\toutputs := result["outputs"].(map[string]any)`,
      ...serveInfo.output_fields.map((f) => `\tfmt.Println(outputs["${f}"])`),
      `}`,
    ].join("\n"),
    dspy:
      pairIndex != null
        ? [
            `import os`,
            `import dspy`,
            `import base64, pickle, requests`,
            ``,
            `# Generate a token in Settings → API and set SKYNET_API_TOKEN in your env`,
            `token = os.environ["SKYNET_API_TOKEN"]`,
            ``,
            `# Fetch the grid result and pick the target pair's artifact`,
            `grid = requests.get(`,
            `    "${gridResultUrl}",`,
            `    headers={"Authorization": f"Bearer {token}"},`,
            `).json()`,
            `pair = next(p for p in grid["pair_results"] if p["pair_index"] == ${pairIndex})`,
            ``,
            `# Deserialize the compiled program from the pair artifact`,
            `program = pickle.loads(`,
            `    base64.b64decode(pair["program_artifact"]["program_pickle_base64"])`,
            `)`,
            ``,
            `# Configure your language model and run the program`,
            `lm = dspy.LM("${model}")`,
            `with dspy.context(lm=lm):`,
            `    result = program(${serveInfo.input_fields
              .map((f) => `${f}=${JSON.stringify(valueFor(f))}`)
              .join(", ")})`,
            ...serveInfo.output_fields.map((f) => `    print(result.${f})`),
          ].join("\n")
        : [
            `import os`,
            `import dspy`,
            `import base64, pickle, requests`,
            ``,
            `# Generate a token in Settings → API and set SKYNET_API_TOKEN in your env`,
            `token = os.environ["SKYNET_API_TOKEN"]`,
            ``,
            `# Download the optimized program artifact`,
            `artifact = requests.get(`,
            `    "${artifactUrl}",`,
            `    headers={"Authorization": f"Bearer {token}"},`,
            `).json()`,
            ``,
            `# Deserialize the compiled program from the artifact`,
            `program = pickle.loads(`,
            `    base64.b64decode(artifact["program_artifact"]["program_pickle_base64"])`,
            `)`,
            ``,
            `# Configure your language model and run the program`,
            `lm = dspy.LM("${model}")`,
            `with dspy.context(lm=lm):`,
            `    result = program(${serveInfo.input_fields
              .map((f) => `${f}=${JSON.stringify(valueFor(f))}`)
              .join(", ")})`,
            ...serveInfo.output_fields.map((f) => `    print(result.${f})`),
          ].join("\n"),
  };
  const labels = {
    curl: "cURL",
    python: "Python",
    javascript: "JavaScript",
    go: "Go",
    dspy: "DSPy",
  } as const;
  const snippet = snippets[codeTab];
  return (
    <CodeEditor
      value={snippet}
      onChange={() => {}}
      height={`${(snippet.split("\n").length + 1) * 19.6 + 8}px`}
      readOnly
      label={<LangPicker value={codeTab} onChange={setCodeTab} labels={labels} />}
    />
  );
}
