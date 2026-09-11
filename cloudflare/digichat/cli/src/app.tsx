import { useMemo } from "react";
import { homedir } from "node:os";
import { Box, Text } from "ink";
import {
  AssistantRuntimeProvider,
  AuiConfig,
  StatusBarPrimitive,
  Tools,
  useLocalRuntime,
} from "@assistant-ui/react-ink";
import { useChatRuntime } from "@assistant-ui/ai-sdk";
import { Thread } from "./components/thread.js";
import { createScriptedAdapter, MODEL_NAME } from "./scripted-adapter.js";
import toolkit from "./tools.js";
import { createDigichatTransport } from "./transport.js";
import type { DigichatCliRequestOptions } from "./chat-request.js";

const config = AuiConfig({
  tools: Tools({ toolkit }),
});

const StatusBar = ({ modelName }: { modelName: string }) => (
  <StatusBarPrimitive.Root>
    <Text dimColor>
      model: <StatusBarPrimitive.ModelName name={modelName} /> ·{" "}
      <StatusBarPrimitive.MessageCount /> · <StatusBarPrimitive.Status />
    </Text>
  </StatusBarPrimitive.Root>
);

function shortCwd(): string {
  const home = homedir();
  const cwd = process.cwd();
  return cwd.startsWith(home) ? `~${cwd.slice(home.length)}` : cwd;
}

/** Official Xulux / with-react-ink starter — scripted coding-agent demo. */
export const DemoInkApp = () => {
  const adapter = useMemo(() => createScriptedAdapter(), []);
  const runtime = useLocalRuntime(adapter);

  return (
    <AssistantRuntimeProvider runtime={runtime} config={config}>
      <Box flexDirection="column" padding={1}>
        <Box>
          <Text bold color="cyan">
            demo-agent
          </Text>
          <Text dimColor>{"  ~/acme-app"}</Text>
        </Box>
        <StatusBar modelName={MODEL_NAME} />
        <Box marginTop={1}>
          <Thread />
        </Box>
      </Box>
    </AssistantRuntimeProvider>
  );
};

const LiveEmptyState = () => (
  <Box flexDirection="column" marginBottom={1}>
    <Text>
      Same BFF as the web embed. Type a question and press Enter.
    </Text>
    <Text dimColor>{'  try: "What is digichat?"'}</Text>
  </Box>
);

/** Live terminal UI — official Ink primitives + AssistantChatTransport. */
export const LiveInkApp = ({
  request,
  modelName,
}: {
  request: DigichatCliRequestOptions;
  modelName: string;
}) => {
  const transport = useMemo(
    () => createDigichatTransport(request),
    [
      request.baseUrl,
      request.auth,
      request.language,
      request.model,
      request.sessionId,
    ],
  );
  const runtime = useChatRuntime({ transport });

  return (
    <AssistantRuntimeProvider runtime={runtime} config={config}>
      <Box flexDirection="column" padding={1}>
        <Box>
          <Text bold color="cyan">
            digichat
          </Text>
          <Text dimColor>{`  ${shortCwd()}`}</Text>
        </Box>
        <StatusBar modelName={modelName} />
        <Box marginTop={1}>
          <Thread emptyState={<LiveEmptyState />} />
        </Box>
      </Box>
    </AssistantRuntimeProvider>
  );
};

export function DigichatCliApp(
  props:
    | { mode: "demo" }
    | { mode: "live"; request: DigichatCliRequestOptions; modelName: string },
) {
  if (props.mode === "demo") return <DemoInkApp />;
  return <LiveInkApp request={props.request} modelName={props.modelName} />;
}
