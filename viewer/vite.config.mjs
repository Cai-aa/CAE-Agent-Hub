import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const DEFAULT_VIEWER_PORT = 4178;
const DEFAULT_CAE_DIRECTORY = "models/text-to-cae";
const RUNNABLE_CAE_CASES = new Map([
  ["models/text-to-cae-hole-plate", {
    solveScript: "hole_plate_abaqus.py",
    exportScript: "export_result_mesh.py",
  }],
  ["models/text-to-cae-hole-plate-modal", {
    solveScript: "hole_plate_modal_abaqus.py",
    exportScript: "export_modal_mesh.py",
  }],
  ["models/text-to-cae-sphere-impact", {
    solveScript: "sphere_impact_abaqus.py",
    exportScript: "export_dynamic_mesh.py",
  }],
  ["models/text-to-cae-milling-3d", {
    solveScript: "milling_abaqus.py",
    exportScript: "export_milling_mesh.py",
  }],
  ["models/text-to-cae-gear-mesh", {
    solveScript: "gear_mesh_abaqus.py",
    exportScript: "export_gear_mesh.py",
  }],
  ["models/text-to-cae-bullet-plate", {
    solveScript: "bullet_plate_penetration_abaqus.py",
    exportScript: "export_bullet_mesh.py",
  }],
]);

const ABAQUS_COMMAND = process.env.ABAQUS_COMMAND || "G:\\SIMULIA\\Commands\\abaqus.bat";
const resolvedPort = Number.parseInt(process.env.VIEWER_PORT || process.env.GUI_PORT || process.env.PORT || "", 10);
const viewerPort = Number.isFinite(resolvedPort) ? resolvedPort : DEFAULT_VIEWER_PORT;
const viewerRoot = process.cwd();
const repoRoot = path.resolve(viewerRoot, "..");

function sendJson(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.end(JSON.stringify(payload));
}

function normalizeRepoDirectory(value, fallbackDir) {
  const rawValue = String(value || "").trim() || fallbackDir;
  const slashNormalized = rawValue.replace(/\\/g, "/").replace(/^\/+/, "");
  const normalized = path.posix.normalize(slashNormalized);
  if (!normalized || normalized === ".") {
    return fallbackDir;
  }
  if (normalized === ".." || normalized.startsWith("../")) {
    throw new Error(`Directory must stay inside the repository: ${rawValue}`);
  }
  return normalized.replace(/\/+$/, "");
}

function resolveRepoDirectory(dir, fallbackDir = DEFAULT_CAE_DIRECTORY) {
  const normalizedDir = normalizeRepoDirectory(dir, fallbackDir);
  const rootPath = path.resolve(repoRoot, normalizedDir);
  const relativePath = path.relative(repoRoot, rootPath);
  if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    throw new Error(`Directory must stay inside the repository: ${normalizedDir}`);
  }
  return {
    dir: normalizedDir,
    rootPath,
  };
}

function readJsonFile(filePath) {
  const payload = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`Expected JSON object in ${filePath}`);
  }
  return payload;
}

function toFiniteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function summarizeResultMesh(mesh) {
  const dynamicFrames = Array.isArray(mesh.dynamicFrames) ? mesh.dynamicFrames : [];
  const modalFrames = Array.isArray(mesh.modalFrames) ? mesh.modalFrames : [];
  const frames = dynamicFrames.length > 0 ? dynamicFrames : modalFrames;
  const baseFrames = frames.length > 0 ? frames : [mesh];
  const history = baseFrames.map((frame, index) => {
    const fieldRanges = frame?.fieldRanges || {};
    return {
      frame: toFiniteNumber(frame?.frame ?? frame?.mode ?? index, index),
      timeMs: toFiniteNumber(frame?.timeMs, 0),
      mode: frame?.mode,
      frequencyHz: Number.isFinite(Number(frame?.frequencyHz)) ? Number(frame.frequencyHz) : undefined,
      maxMises: toFiniteNumber(fieldRanges.misesMax ?? fieldRanges.valueMax, 0),
      minMises: toFiniteNumber(fieldRanges.misesMin ?? fieldRanges.valueMin, 0),
      maxDisplacement: toFiniteNumber(fieldRanges.maxDisplacement, 0),
      toolX: Number.isFinite(Number(frame?.toolPose?.x)) ? Number(frame.toolPose.x) : undefined,
      contactRadiusMm: Number.isFinite(Number(frame?.contact?.contactRadiusMm)) ? Number(frame.contact.contactRadiusMm) : undefined,
      indentationMm: Number.isFinite(Number(frame?.contact?.indentationMm)) ? Number(frame.contact.indentationMm) : undefined,
    };
  });
  const elementTypes = {};
  const sampleElements = Array.isArray(mesh.elements) ? mesh.elements : [];
  for (const element of sampleElements) {
    const type = String(element?.type || mesh.elementType || "Unknown");
    elementTypes[type] = (elementTypes[type] || 0) + 1;
  }
  return {
    analysisType: mesh.analysisType || "static",
    source: mesh.source || "",
    instance: mesh.instance || "",
    step: mesh.step || "",
    elementType: mesh.elementType || "",
    frameCount: baseFrames.length,
    nodeCount: Array.isArray(mesh.nodes) ? mesh.nodes.length : 0,
    elementCount: sampleElements.length,
    elementTypes,
    fieldRanges: mesh.fieldRanges || {},
    history,
  };
}

function writeJsonFile(filePath, payload) {
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.setEncoding("utf8");
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 100_000) {
        reject(new Error("Request body is too large"));
        req.destroy();
      }
    });
    req.on("end", () => resolve(body));
    req.on("error", reject);
  });
}

function parameterNumber(value, fallback, { min, max }) {
  const number = Number(value);
  const finite = Number.isFinite(number) ? number : fallback;
  return Math.min(Math.max(finite, min), max);
}

function normalizeCaeParameters(rawParameters = {}, caeDir = "") {
  const isF22Flow = caeDir === "models/text-to-cae-f22-flow";
  const isMilling = caeDir === "models/text-to-cae-milling-3d";
  const isGearMesh = caeDir === "models/text-to-cae-gear-mesh";
  if (isF22Flow) {
    return {
      length_m: parameterNumber(rawParameters.length_m, 18.9, { min: 10, max: 30 }),
      wingspan_m: parameterNumber(rawParameters.wingspan_m, 13.6, { min: 8, max: 24 }),
      mach: parameterNumber(rawParameters.mach, 0.85, { min: 0.2, max: 1.4 }),
      altitude_m: parameterNumber(rawParameters.altitude_m, 10000, { min: 0, max: 18000 }),
      angle_of_attack_deg: parameterNumber(rawParameters.angle_of_attack_deg, 3, { min: -6, max: 18 }),
      sideslip_deg: parameterNumber(rawParameters.sideslip_deg, 0, { min: -10, max: 10 }),
      reference_area_m2: parameterNumber(rawParameters.reference_area_m2, 78, { min: 20, max: 160 }),
      dynamic_pressure_pa: parameterNumber(rawParameters.dynamic_pressure_pa, 14800, { min: 1000, max: 90000 }),
    };
  }
  if (isGearMesh) {
    return {
      module_mm: parameterNumber(rawParameters.module_mm, 2.5, { min: 0.8, max: 6 }),
      driver_teeth: Math.round(parameterNumber(rawParameters.driver_teeth, 18, { min: 10, max: 40 })),
      driven_teeth: Math.round(parameterNumber(rawParameters.driven_teeth, 30, { min: 10, max: 60 })),
      face_width_mm: parameterNumber(rawParameters.face_width_mm, 12, { min: 4, max: 35 }),
      driver_speed_rpm: parameterNumber(rawParameters.driver_speed_rpm, 900, { min: 30, max: 3600 }),
      transmitted_torque_nmm: parameterNumber(rawParameters.transmitted_torque_nmm, 1800, { min: 50, max: 20000 }),
      pressure_angle_deg: parameterNumber(rawParameters.pressure_angle_deg, 20, { min: 14.5, max: 25 }),
      backlash_mm: parameterNumber(rawParameters.backlash_mm, 0.08, { min: 0, max: 0.5 }),
      step_time_s: parameterNumber(rawParameters.step_time_s, 0.04, { min: 0.005, max: 0.12 }),
      output_frames: Math.round(parameterNumber(rawParameters.output_frames, 120, { min: 40, max: 240 })),
      seed_size_mm: parameterNumber(rawParameters.seed_size_mm, 1.2, { min: 0.4, max: 5 }),
      youngs_modulus_mpa: parameterNumber(rawParameters.youngs_modulus_mpa, 210000, { min: 1000, max: 500000 }),
      poissons_ratio: parameterNumber(rawParameters.poissons_ratio, 0.3, { min: 0.01, max: 0.49 }),
    };
  }
  if (isMilling) {
    const workpieceLength = parameterNumber(rawParameters.workpiece_length_mm, 56, { min: 24, max: 80 });
    const workpieceWidth = parameterNumber(rawParameters.workpiece_width_mm, 24, { min: 10, max: 45 });
    const workpieceThickness = parameterNumber(rawParameters.workpiece_thickness_mm, 8, { min: 3, max: 14 });
    const toolDiameter = parameterNumber(rawParameters.tool_diameter_mm, 8, { min: 3, max: Math.min(18, workpieceWidth * 0.85) });
    return {
      workpiece_length_mm: workpieceLength,
      workpiece_width_mm: workpieceWidth,
      workpiece_thickness_mm: workpieceThickness,
      tool_diameter_mm: toolDiameter,
      flute_count: Math.round(parameterNumber(rawParameters.flute_count, 4, { min: 2, max: 6 })),
      spindle_speed_rpm: parameterNumber(rawParameters.spindle_speed_rpm, 9000, { min: 1000, max: 30000 }),
      feed_per_tooth_mm: parameterNumber(rawParameters.feed_per_tooth_mm, 0.035, { min: 0.005, max: 0.18 }),
      axial_depth_mm: parameterNumber(rawParameters.axial_depth_mm, 3, { min: 0.4, max: Math.min(workpieceThickness * 0.85, 8) }),
      radial_width_mm: parameterNumber(rawParameters.radial_width_mm, 8, { min: 0.6, max: Math.min(toolDiameter, workpieceWidth * 0.75) }),
      step_time_s: parameterNumber(rawParameters.step_time_s, 0.0014, { min: 0.0002, max: 0.004 }),
      output_frames: Math.round(parameterNumber(rawParameters.output_frames, 240, { min: 80, max: 500 })),
      seed_size_mm: parameterNumber(rawParameters.seed_size_mm, 1, { min: 0.8, max: 3.5 }),
      youngs_modulus_mpa: parameterNumber(rawParameters.youngs_modulus_mpa, 71000, { min: 1000, max: 500000 }),
      poissons_ratio: parameterNumber(rawParameters.poissons_ratio, 0.33, { min: 0.01, max: 0.49 }),
    };
  }
  const length = parameterNumber(rawParameters.length_mm, 120, { min: 40, max: 300 });
  const width = parameterNumber(rawParameters.width_mm, 60, { min: 20, max: 180 });
  const thickness = parameterNumber(rawParameters.thickness_mm, 4, { min: 1, max: 30 });
  const maxHoleRadius = Math.max(2, Math.min(length, width) * 0.38);
  return {
    length_mm: length,
    width_mm: width,
    thickness_mm: thickness,
    hole_radius_mm: parameterNumber(rawParameters.hole_radius_mm, 12, { min: 2, max: maxHoleRadius }),
    ball_radius_mm: parameterNumber(rawParameters.ball_radius_mm, 8, { min: 3, max: Math.max(3, Math.min(length, width) * 0.22) }),
    impact_velocity_mps: parameterNumber(rawParameters.impact_velocity_mps, 28, { min: 2, max: 120 }),
    right_displacement_x_mm: parameterNumber(rawParameters.right_displacement_x_mm, 0.12, { min: 0.005, max: 2 }),
    seed_size_mm: parameterNumber(rawParameters.seed_size_mm, 3, { min: 1, max: 12 }),
    youngs_modulus_mpa: parameterNumber(rawParameters.youngs_modulus_mpa, 210000, { min: 1000, max: 500000 }),
    poissons_ratio: parameterNumber(rawParameters.poissons_ratio, 0.3, { min: 0.01, max: 0.49 }),
  };
}

function runAbaqusScript(scriptPath, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(ABAQUS_COMMAND, ["cae", `noGUI=${scriptPath}`], {
      cwd,
      shell: true,
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
        return;
      }
      reject(new Error(`Command failed with exit code ${code}: ${stderr || stdout}`));
    });
  });
}

async function runAbaqusCase(rootPath, runConfig) {
  const solveScript = path.join(rootPath, runConfig.solveScript);
  const exportScript = path.join(rootPath, runConfig.exportScript);
  if (!fs.existsSync(solveScript) || !fs.existsSync(exportScript)) {
    throw new Error("Missing Abaqus solve/export scripts for this CAE case.");
  }
  await runAbaqusScript(solveScript, rootPath);
  await runAbaqusScript(exportScript, rootPath);
}

function attachCaeMiddleware(middlewares) {
  middlewares.use((req, res, next) => {
    const requestUrl = new URL(req.url || "/", "http://localhost");
    if (requestUrl.pathname === "/__cae/project") {
      try {
        const resolved = resolveRepoDirectory(requestUrl.searchParams.get("dir"));
        sendJson(res, 200, readJsonFile(path.join(resolved.rootPath, "cae_project.json")));
      } catch (error) {
        sendJson(res, 400, { error: error instanceof Error ? error.message : String(error) });
      }
      return;
    }
    if (requestUrl.pathname === "/__cae/result-mesh") {
      try {
        const resolved = resolveRepoDirectory(requestUrl.searchParams.get("dir"));
        sendJson(res, 200, readJsonFile(path.join(resolved.rootPath, "result_mesh.json")));
      } catch (error) {
        sendJson(res, 400, { error: error instanceof Error ? error.message : String(error) });
      }
      return;
    }
    if (requestUrl.pathname === "/__cae/result-summary") {
      try {
        const resolved = resolveRepoDirectory(requestUrl.searchParams.get("dir"));
        sendJson(res, 200, summarizeResultMesh(readJsonFile(path.join(resolved.rootPath, "result_mesh.json"))));
      } catch (error) {
        sendJson(res, 400, { error: error instanceof Error ? error.message : String(error) });
      }
      return;
    }
    if (requestUrl.pathname === "/__cae/parameters") {
      try {
        const resolved = resolveRepoDirectory(requestUrl.searchParams.get("dir"));
        const parametersPath = path.join(resolved.rootPath, "cae_parameters.json");
        const rawParameters = fs.existsSync(parametersPath) ? readJsonFile(parametersPath) : {};
        sendJson(res, 200, {
          editable: RUNNABLE_CAE_CASES.has(resolved.dir),
          parameters: normalizeCaeParameters(rawParameters, resolved.dir),
        });
      } catch (error) {
        sendJson(res, 400, { error: error instanceof Error ? error.message : String(error) });
      }
      return;
    }
    if (requestUrl.pathname === "/__cae/run") {
      if (req.method !== "POST") {
        sendJson(res, 405, { error: "Method not allowed" });
        return;
      }
      void (async () => {
        try {
          const body = await readRequestBody(req);
          const payload = body ? JSON.parse(body) : {};
          const resolved = resolveRepoDirectory(payload.dir);
          const runConfig = RUNNABLE_CAE_CASES.get(resolved.dir);
          if (!runConfig) {
            throw new Error(`CAE case is not runnable from the browser: ${resolved.dir}`);
          }
          const parameters = normalizeCaeParameters(payload.parameters || {}, resolved.dir);
          writeJsonFile(path.join(resolved.rootPath, "cae_parameters.json"), parameters);
          await runAbaqusCase(resolved.rootPath, runConfig);
          sendJson(res, 200, {
            ok: true,
            parameters,
            project: readJsonFile(path.join(resolved.rootPath, "cae_project.json")),
          });
        } catch (error) {
          sendJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
        }
      })();
      return;
    }
    next();
  });
}

function caeApiPlugin() {
  return {
    name: "text-to-cae-api",
    configureServer(server) {
      attachCaeMiddleware(server.middlewares);
    },
    configurePreviewServer(server) {
      attachCaeMiddleware(server.middlewares);
    },
  };
}

export default defineConfig({
  plugins: [react(), caeApiPlugin()],
  resolve: {
    alias: {
      "@": viewerRoot,
    },
  },
  esbuild: {
    loader: "jsx",
    include: /.*\.[jt]sx?$/,
    exclude: [],
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: {
        ".js": "jsx",
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      input: { main: path.resolve(viewerRoot, "index.html"), peridigm: path.resolve(viewerRoot, "peridigm.html") },
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (id.includes("/three/")) {
            return "vendor-three";
          }
          if (id.includes("/react/") || id.includes("/react-dom/")) {
            return "vendor-react";
          }
          if (id.includes("/radix-ui/") || id.includes("/@radix-ui/")) {
            return "vendor-ui";
          }
          if (id.includes("/lucide-react/")) {
            return "vendor-icons";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: viewerPort,
    strictPort: true,
  },
  preview: {
    host: "127.0.0.1",
    port: viewerPort,
    strictPort: true,
  },
});
