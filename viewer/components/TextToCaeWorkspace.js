import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, FileCode2, LoaderCircle, RefreshCw, TerminalSquare } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import CaeResultViewer from "./CaeResultViewer";
import { fetchCaeParameters, fetchCaeProject, fetchCaeResultSummary, runCaeSimulation } from "../lib/caeProjectStore";

const CAE_CASES = Object.freeze([
  {
    id: "cantilever",
    directory: "models/text-to-cae",
    labels: {
      en: "Cantilever beam",
      zh: "\u60ac\u81c2\u6881",
    },
  },
  {
    id: "hole-plate",
    directory: "models/text-to-cae-hole-plate",
    labels: {
      en: "Plate with hole",
      zh: "\u5e26\u5706\u5b54\u62c9\u4f38\u677f",
    },
  },
  {
    id: "hole-plate-modal",
    directory: "models/text-to-cae-hole-plate-modal",
    labels: {
      en: "Plate modal",
      zh: "\u5e26\u5706\u5b54\u677f\u6a21\u6001",
    },
  },
  {
    id: "sphere-impact",
    directory: "models/text-to-cae-sphere-impact",
    labels: {
      en: "Sphere impact",
      zh: "\u7403\u51b2\u51fb\u677f\u6750",
    },
  },
  {
    id: "milling-3d",
    directory: "models/text-to-cae-milling-3d",
    labels: {
      en: "3D end milling",
      zh: "\u4e09\u7ef4\u7acb\u94e3\u52a8\u529b\u5b66",
    },
  },
  {
    id: "gear-mesh",
    directory: "models/text-to-cae-gear-mesh",
    labels: {
      en: "Gear mesh dynamics",
      zh: "\u9f7f\u8f6e\u556e\u5408\u52a8\u529b\u5b66",
    },
  },
  {
    id: "bullet-plate",
    directory: "models/text-to-cae-bullet-plate",
    labels: {
      en: "Bullet penetration",
      zh: "\u5b50\u5f39\u7a7f\u900f\u94a2\u677f",
    },
  },
  {
    id: "f22-flow",
    directory: "models/text-to-cae-f22-flow",
    labels: {
      en: "F-22 flow field",
      zh: "F-22 \u6d41\u573a",
    },
  },
  {
    id: "calculix-cantilever",
    directory: "models/text-to-cae-calculix-cantilever",
    labels: {
      en: "CalculiX cantilever",
      zh: "CalculiX 悬臂梁",
    },
  },
  {
    id: "calculix-modal",
    directory: "models/text-to-cae-calculix-modal",
    labels: {
      en: "CalculiX cantilever mode 1",
      zh: "CalculiX 悬臂梁一阶振型",
    },
  },
]);

const PARAMETER_FIELDS = Object.freeze([
  {
    key: "length_mm",
    min: 40,
    max: 300,
    step: 1,
    unit: "mm",
    labels: { en: "Plate length", zh: "\u677f\u957f" },
  },
  {
    key: "width_mm",
    min: 20,
    max: 180,
    step: 1,
    unit: "mm",
    labels: { en: "Plate width", zh: "\u677f\u5bbd" },
  },
  {
    key: "thickness_mm",
    min: 1,
    max: 30,
    step: 0.5,
    unit: "mm",
    labels: { en: "Thickness", zh: "\u539a\u5ea6" },
  },
  {
    key: "hole_radius_mm",
    min: 2,
    max: 60,
    step: 0.5,
    unit: "mm",
    labels: { en: "Hole radius", zh: "\u5706\u5b54\u534a\u5f84" },
  },
  {
    key: "ball_radius_mm",
    min: 3,
    max: 40,
    step: 0.5,
    unit: "mm",
    labels: { en: "Sphere radius", zh: "\u7403\u534a\u5f84" },
  },
  {
    key: "impact_velocity_mps",
    min: 2,
    max: 120,
    step: 1,
    unit: "m/s",
    labels: { en: "Impact velocity", zh: "\u51b2\u51fb\u901f\u5ea6" },
  },
  {
    key: "right_displacement_x_mm",
    min: 0.005,
    max: 2,
    step: 0.005,
    unit: "mm",
    labels: { en: "Right displacement X", zh: "\u53f3\u7aef X \u5411\u4f4d\u79fb" },
  },
  {
    key: "seed_size_mm",
    min: 0.8,
    max: 12,
    step: 0.5,
    unit: "mm",
    labels: { en: "Mesh seed", zh: "\u7f51\u683c\u79cd\u5b50" },
  },
  {
    key: "youngs_modulus_mpa",
    min: 1000,
    max: 500000,
    step: 1000,
    unit: "MPa",
    labels: { en: "Young's modulus", zh: "\u5f39\u6027\u6a21\u91cf" },
  },
  {
    key: "poissons_ratio",
    min: 0.01,
    max: 0.49,
    step: 0.01,
    unit: "",
    labels: { en: "Poisson's ratio", zh: "\u6cca\u677e\u6bd4" },
  },
  {
    key: "workpiece_length_mm",
    min: 24,
    max: 80,
    step: 1,
    unit: "mm",
    labels: { en: "Workpiece length", zh: "\u5de5\u4ef6\u957f\u5ea6" },
  },
  {
    key: "workpiece_width_mm",
    min: 10,
    max: 45,
    step: 1,
    unit: "mm",
    labels: { en: "Workpiece width", zh: "\u5de5\u4ef6\u5bbd\u5ea6" },
  },
  {
    key: "workpiece_thickness_mm",
    min: 3,
    max: 14,
    step: 0.5,
    unit: "mm",
    labels: { en: "Workpiece thickness", zh: "\u5de5\u4ef6\u539a\u5ea6" },
  },
  {
    key: "tool_diameter_mm",
    min: 3,
    max: 18,
    step: 0.5,
    unit: "mm",
    labels: { en: "Tool diameter", zh: "\u5200\u5177\u76f4\u5f84" },
  },
  {
    key: "flute_count",
    min: 2,
    max: 6,
    step: 1,
    unit: "",
    labels: { en: "Flutes", zh: "\u5203\u6570" },
  },
  {
    key: "spindle_speed_rpm",
    min: 1000,
    max: 30000,
    step: 500,
    unit: "rpm",
    labels: { en: "Spindle speed", zh: "\u4e3b\u8f74\u8f6c\u901f" },
  },
  {
    key: "feed_per_tooth_mm",
    min: 0.005,
    max: 0.18,
    step: 0.005,
    unit: "mm/tooth",
    labels: { en: "Feed per tooth", zh: "\u6bcf\u9f7f\u8fdb\u7ed9" },
  },
  {
    key: "axial_depth_mm",
    min: 0.4,
    max: 8,
    step: 0.1,
    unit: "mm",
    labels: { en: "Axial depth", zh: "\u8f74\u5411\u5207\u6df1" },
  },
  {
    key: "radial_width_mm",
    min: 0.6,
    max: 18,
    step: 0.1,
    unit: "mm",
    labels: { en: "Radial engagement", zh: "\u5f84\u5411\u5403\u5200" },
  },
  {
    key: "step_time_s",
    min: 0.0002,
    max: 0.004,
    step: 0.0001,
    unit: "s",
    labels: { en: "Simulation time", zh: "\u4eff\u771f\u65f6\u957f" },
  },
  {
    key: "output_frames",
    min: 80,
    max: 500,
    step: 10,
    unit: "",
    labels: { en: "Output frames", zh: "\u8f93\u51fa\u5e27\u6570" },
  },
  {
    key: "length_m",
    min: 10,
    max: 30,
    step: 0.1,
    unit: "m",
    labels: { en: "Aircraft length", zh: "\u98de\u673a\u957f\u5ea6" },
  },
  {
    key: "wingspan_m",
    min: 8,
    max: 24,
    step: 0.1,
    unit: "m",
    labels: { en: "Wingspan", zh: "\u7ffc\u5c55" },
  },
  {
    key: "mach",
    min: 0.2,
    max: 1.4,
    step: 0.01,
    unit: "",
    labels: { en: "Mach number", zh: "\u9a6c\u8d6b\u6570" },
  },
  {
    key: "altitude_m",
    min: 0,
    max: 18000,
    step: 250,
    unit: "m",
    labels: { en: "Altitude", zh: "\u9ad8\u5ea6" },
  },
  {
    key: "angle_of_attack_deg",
    min: -6,
    max: 18,
    step: 0.25,
    unit: "deg",
    labels: { en: "Angle of attack", zh: "\u8fce\u89d2" },
  },
  {
    key: "sideslip_deg",
    min: -10,
    max: 10,
    step: 0.25,
    unit: "deg",
    labels: { en: "Sideslip", zh: "\u4fa7\u6ed1\u89d2" },
  },
  {
    key: "reference_area_m2",
    min: 20,
    max: 160,
    step: 1,
    unit: "m2",
    labels: { en: "Reference area", zh: "\u53c2\u8003\u9762\u79ef" },
  },
  {
    key: "dynamic_pressure_pa",
    min: 1000,
    max: 90000,
    step: 500,
    unit: "Pa",
    labels: { en: "Dynamic pressure", zh: "\u52a8\u538b" },
  },
  {
    key: "module_mm",
    min: 0.8,
    max: 6,
    step: 0.1,
    unit: "mm",
    labels: { en: "Gear module", zh: "\u9f7f\u8f6e\u6a21\u6570" },
  },
  {
    key: "driver_teeth",
    min: 10,
    max: 40,
    step: 1,
    unit: "",
    labels: { en: "Driver teeth", zh: "\u4e3b\u52a8\u8f6e\u9f7f\u6570" },
  },
  {
    key: "driven_teeth",
    min: 10,
    max: 60,
    step: 1,
    unit: "",
    labels: { en: "Driven teeth", zh: "\u4ece\u52a8\u8f6e\u9f7f\u6570" },
  },
  {
    key: "face_width_mm",
    min: 4,
    max: 35,
    step: 0.5,
    unit: "mm",
    labels: { en: "Face width", zh: "\u9f7f\u5bbd" },
  },
  {
    key: "driver_speed_rpm",
    min: 30,
    max: 3600,
    step: 30,
    unit: "rpm",
    labels: { en: "Driver speed", zh: "\u4e3b\u52a8\u8f6e\u8f6c\u901f" },
  },
  {
    key: "transmitted_torque_nmm",
    min: 50,
    max: 20000,
    step: 50,
    unit: "N mm",
    labels: { en: "Torque", zh: "\u4f20\u9012\u626d\u77e9" },
  },
  {
    key: "pressure_angle_deg",
    min: 14.5,
    max: 25,
    step: 0.5,
    unit: "deg",
    labels: { en: "Pressure angle", zh: "\u538b\u529b\u89d2" },
  },
  {
    key: "backlash_mm",
    min: 0,
    max: 0.5,
    step: 0.01,
    unit: "mm",
    labels: { en: "Backlash", zh: "\u4fa7\u9699" },
  },
]);

const CAE_TEXT = Object.freeze({
  en: {
    appLabel: "Text to CAE",
    loadingProject: "Loading CAE project",
    refresh: "Refresh",
    loadErrorTitle: "CAE project failed to load",
    loadingPrompt: "Loading prompt...",
    modelFallback: "Static solid mechanics",
    copyCommand: "Copy command",
    copyTitle: "Copy Abaqus command",
    copied: "Copied",
    copyFailed: "Copy failed",
    pending: "Pending",
    workflowTitle: "Abaqus workflow",
    inputsTitle: "Simulation inputs",
    parametersTitle: "Editable parameters",
    modelTreeTitle: "Model Tree",
    projectTreeTitle: "Projects",
    metricsTitle: "Result metrics",
    selectedTreeTitle: "Selected tree item",
    historyOutputTitle: "History output",
    fieldOutputTitle: "Field output",
    noHistoryData: "No result history loaded",
    commandTitle: "Abaqus command",
    modelTreeRoot: "Model Database",
    modelTreeModel: "Model",
    modelTreeParts: "Parts",
    modelTreeMaterials: "Materials",
    modelTreeAssembly: "Assembly",
    modelTreeSteps: "Steps",
    modelTreeInteractions: "Interactions",
    modelTreeLoads: "Loads",
    modelTreeBcs: "BCs",
    modelTreeMesh: "Mesh",
    modelTreeJobs: "Jobs",
    modelTreeResults: "Results",
    runSimulation: "Run Abaqus",
    runningSimulation: "Running Abaqus...",
    runComplete: "Simulation complete. Results refreshed.",
    runFailed: "Simulation failed",
    caseLabel: "Case",
    connection: "Abaqus connection",
    loadingConnection: "Loading connection status...",
    languageLabel: "Language",
    english: "EN",
    chinese: "\u4e2d\u6587",
    status: {
      blocked: "blocked",
      building: "building",
      complete: "complete",
      connected: "connected",
      error: "error",
      failed: "failed",
      loading: "loading",
      pending: "pending",
      ready: "ready",
      running: "running",
      unavailable: "unavailable",
    },
    metricLabels: {
      "Max von Mises stress": "Max von Mises stress",
      "Max displacement magnitude": "Max displacement magnitude",
      "Tip displacement Y": "Tip displacement Y",
      "Right edge displacement X": "Right edge displacement X",
      "Stress concentration factor": "Stress concentration factor",
      "Mode 1 frequency": "Mode 1 frequency",
      "Mode 2 frequency": "Mode 2 frequency",
      "Mode 3 frequency": "Mode 3 frequency",
      "Mode 4 frequency": "Mode 4 frequency",
      "Peak von Mises stress": "Peak von Mises stress",
      "Peak center deflection": "Peak center deflection",
      "Impact duration": "Impact duration",
      "Displayed frames": "Displayed frames",
      "Peak milling stress": "Peak milling stress",
      "Max workpiece displacement": "Max workpiece displacement",
      "Spindle speed": "Spindle speed",
    },
    inputLabels: {
      geometry: "Geometry",
      material: "Material",
      boundaryLoad: "Boundary and load",
      mesh: "Mesh",
    },
    workflow: {
      "Parse prompt": {
        step: "Parse prompt",
        detail: "The natural language request is mapped to geometry, material, boundary conditions, loading, and a static step.",
      },
      "Build Abaqus model": {
        step: "Build Abaqus model",
        detail: "The Abaqus script creates the part, material, section, assembly, sets, load, mesh, and job.",
      },
      Solve: {
        step: "Solve",
        detail: "Abaqus/CAE noGUI ran the static job and produced an ODB result database.",
      },
      "Review results": {
        step: "Review results",
        detail: "After the job completes, the script extracts stress and displacement results from the ODB.",
      },
    },
    connectionMessages: {
      "Abaqus solved the model and extracted ODB results.": "Abaqus solved the model and extracted ODB results.",
      "Abaqus solved the modal model and extracted ODB results.": "Abaqus solved the modal model and extracted ODB results.",
      "Abaqus modal analysis is ready to run.": "Abaqus modal analysis is ready to run.",
      "Abaqus solved the sphere impact model and extracted ODB results.": "Abaqus solved the sphere impact model and extracted ODB results.",
      "Abaqus sphere impact analysis is ready to run.": "Abaqus sphere impact analysis is ready to run.",
      "Abaqus solved the 3D milling dynamics model and extracted ODB results.": "Abaqus solved the 3D milling dynamics model and extracted ODB results.",
      "Abaqus 3D milling dynamics analysis is ready to run.": "Abaqus 3D milling dynamics analysis is ready to run.",
    },
  },
  zh: {
    appLabel: "Text to CAE",
    loadingProject: "\u6b63\u5728\u52a0\u8f7d CAE \u9879\u76ee",
    refresh: "\u5237\u65b0",
    loadErrorTitle: "CAE \u9879\u76ee\u52a0\u8f7d\u5931\u8d25",
    loadingPrompt: "\u6b63\u5728\u52a0\u8f7d\u4eff\u771f\u63cf\u8ff0...",
    modelFallback: "\u9759\u529b\u7ed3\u6784\u529b\u5b66",
    copyCommand: "\u590d\u5236\u547d\u4ee4",
    copyTitle: "\u590d\u5236 Abaqus \u547d\u4ee4",
    copied: "\u5df2\u590d\u5236",
    copyFailed: "\u590d\u5236\u5931\u8d25",
    pending: "\u5f85\u751f\u6210",
    workflowTitle: "Abaqus \u5de5\u4f5c\u6d41",
    inputsTitle: "\u4eff\u771f\u8f93\u5165",
    parametersTitle: "\u53ef\u7f16\u8f91\u53c2\u6570",
    modelTreeTitle: "\u6a21\u578b\u6811",
    projectTreeTitle: "\u9879\u76ee",
    metricsTitle: "\u7ed3\u679c\u6307\u6807",
    selectedTreeTitle: "\u5f53\u524d\u9009\u4e2d\u6811\u8282\u70b9",
    historyOutputTitle: "\u5386\u53f2\u8f93\u51fa",
    fieldOutputTitle: "\u573a\u8f93\u51fa",
    noHistoryData: "\u5c1a\u672a\u52a0\u8f7d\u7ed3\u679c\u5386\u53f2",
    commandTitle: "Abaqus \u547d\u4ee4",
    modelTreeRoot: "\u6a21\u578b\u6570\u636e\u5e93",
    modelTreeModel: "\u6a21\u578b",
    modelTreeParts: "\u96f6\u4ef6",
    modelTreeMaterials: "\u6750\u6599",
    modelTreeAssembly: "\u88c5\u914d",
    modelTreeSteps: "\u5206\u6790\u6b65",
    modelTreeInteractions: "\u76f8\u4e92\u4f5c\u7528",
    modelTreeLoads: "\u8f7d\u8377",
    modelTreeBcs: "\u8fb9\u754c\u6761\u4ef6",
    modelTreeMesh: "\u7f51\u683c",
    modelTreeJobs: "\u4f5c\u4e1a",
    modelTreeResults: "\u7ed3\u679c",
    runSimulation: "\u91cd\u65b0\u8fd0\u7b97",
    runningSimulation: "Abaqus \u6b63\u5728\u8fd0\u7b97...",
    runComplete: "\u8fd0\u7b97\u5b8c\u6210\uff0c\u7ed3\u679c\u5df2\u5237\u65b0\u3002",
    runFailed: "\u8fd0\u7b97\u5931\u8d25",
    caseLabel: "\u7b97\u4f8b",
    connection: "Abaqus \u8fde\u63a5",
    loadingConnection: "\u6b63\u5728\u52a0\u8f7d\u8fde\u63a5\u72b6\u6001...",
    languageLabel: "\u8bed\u8a00",
    english: "EN",
    chinese: "\u4e2d\u6587",
    status: {
      blocked: "\u53d7\u963b",
      building: "\u5efa\u6a21\u4e2d",
      complete: "\u5b8c\u6210",
      connected: "\u5df2\u8fde\u63a5",
      error: "\u9519\u8bef",
      failed: "\u5931\u8d25",
      loading: "\u52a0\u8f7d\u4e2d",
      pending: "\u5f85\u5904\u7406",
      ready: "\u5c31\u7eea",
      running: "\u8fd0\u884c\u4e2d",
      unavailable: "\u4e0d\u53ef\u7528",
    },
    metricLabels: {
      "Max von Mises stress": "\u6700\u5927 von Mises \u5e94\u529b",
      "Max displacement magnitude": "\u6700\u5927\u4f4d\u79fb\u5e45\u503c",
      "Tip displacement Y": "\u7aef\u90e8 Y \u5411\u4f4d\u79fb",
      "Right edge displacement X": "\u53f3\u8fb9 X \u5411\u4f4d\u79fb",
      "Stress concentration factor": "\u5e94\u529b\u96c6\u4e2d\u7cfb\u6570",
      "Mode 1 frequency": "1 \u9636\u56fa\u6709\u9891\u7387",
      "Mode 2 frequency": "2 \u9636\u56fa\u6709\u9891\u7387",
      "Mode 3 frequency": "3 \u9636\u56fa\u6709\u9891\u7387",
      "Mode 4 frequency": "4 \u9636\u56fa\u6709\u9891\u7387",
      "Peak von Mises stress": "\u5cf0\u503c von Mises \u5e94\u529b",
      "Peak center deflection": "\u4e2d\u5fc3\u5cf0\u503c\u6320\u5ea6",
      "Impact duration": "\u51b2\u51fb\u65f6\u957f",
      "Displayed frames": "\u663e\u793a\u5e27\u6570",
      "Peak milling stress": "\u5cf0\u503c\u94e3\u524a\u5e94\u529b",
      "Max workpiece displacement": "\u6700\u5927\u5de5\u4ef6\u4f4d\u79fb",
      "Spindle speed": "\u4e3b\u8f74\u8f6c\u901f",
    },
    inputLabels: {
      geometry: "\u51e0\u4f55",
      material: "\u6750\u6599",
      boundaryLoad: "\u8fb9\u754c\u4e0e\u8f7d\u8377",
      mesh: "\u7f51\u683c",
    },
    workflow: {
      "Parse prompt": {
        step: "\u89e3\u6790\u63cf\u8ff0",
        detail: "\u5c06\u81ea\u7136\u8bed\u8a00\u8bf7\u6c42\u6620\u5c04\u4e3a\u51e0\u4f55\u3001\u6750\u6599\u3001\u8fb9\u754c\u6761\u4ef6\u3001\u8f7d\u8377\u548c\u9759\u529b\u5206\u6790\u6b65\u3002",
      },
      "Build Abaqus model": {
        step: "\u521b\u5efa Abaqus \u6a21\u578b",
        detail: "Abaqus \u811a\u672c\u521b\u5efa\u96f6\u4ef6\u3001\u6750\u6599\u3001\u622a\u9762\u3001\u88c5\u914d\u3001\u96c6\u5408\u3001\u8f7d\u8377\u3001\u7f51\u683c\u548c\u4f5c\u4e1a\u3002",
      },
      Solve: {
        step: "\u6c42\u89e3",
        detail: "Abaqus/CAE noGUI \u8fd0\u884c\u9759\u529b\u4f5c\u4e1a\uff0c\u5e76\u751f\u6210 ODB \u7ed3\u679c\u6570\u636e\u5e93\u3002",
      },
      "Review results": {
        step: "\u67e5\u770b\u7ed3\u679c",
        detail: "\u4f5c\u4e1a\u5b8c\u6210\u540e\uff0c\u811a\u672c\u4ece ODB \u4e2d\u63d0\u53d6\u5e94\u529b\u548c\u4f4d\u79fb\u7ed3\u679c\u3002",
      },
    },
    connectionMessages: {
      "Abaqus solved the model and extracted ODB results.": "Abaqus \u5df2\u5b8c\u6210\u6c42\u89e3\uff0c\u5e76\u4ece ODB \u4e2d\u63d0\u53d6\u7ed3\u679c\u3002",
      "Abaqus solved the modal model and extracted ODB results.": "Abaqus \u5df2\u5b8c\u6210\u6a21\u6001\u6c42\u89e3\uff0c\u5e76\u4ece ODB \u4e2d\u63d0\u53d6\u7ed3\u679c\u3002",
      "Abaqus modal analysis is ready to run.": "Abaqus \u6a21\u6001\u5206\u6790\u5df2\u51c6\u5907\u8fd0\u884c\u3002",
      "Abaqus solved the sphere impact model and extracted ODB results.": "Abaqus \u5df2\u5b8c\u6210\u7403\u51b2\u51fb\u677f\u6750\u52a8\u529b\u5b66\u6c42\u89e3\uff0c\u5e76\u4ece ODB \u4e2d\u63d0\u53d6\u7ed3\u679c\u3002",
      "Abaqus sphere impact analysis is ready to run.": "Abaqus \u7403\u51b2\u51fb\u663e\u5f0f\u52a8\u529b\u5b66\u5206\u6790\u5df2\u51c6\u5907\u8fd0\u884c\u3002",
      "Abaqus solved the 3D milling dynamics model and extracted ODB results.": "Abaqus \u5df2\u5b8c\u6210\u4e09\u7ef4\u94e3\u524a\u52a8\u529b\u5b66\u6c42\u89e3\uff0c\u5e76\u4ece ODB \u4e2d\u63d0\u53d6\u7ed3\u679c\u3002",
      "Abaqus 3D milling dynamics analysis is ready to run.": "Abaqus \u4e09\u7ef4\u94e3\u524a\u52a8\u529b\u5b66\u5206\u6790\u5df2\u51c6\u5907\u8fd0\u884c\u3002",
    },
  },
});

function getInitialCaseId() {
  if (typeof window === "undefined") {
    return CAE_CASES[0].id;
  }
  const params = new URLSearchParams(window.location.search);
  const fromCase = params.get("case");
  if (CAE_CASES.some((item) => item.id === fromCase)) {
    return fromCase;
  }
  const fromDir = params.get("caeDir");
  const match = CAE_CASES.find((item) => item.directory === fromDir);
  if (match) {
    return match.id;
  }
  const savedCase = window.localStorage.getItem("text-to-cae-case");
  if (CAE_CASES.some((item) => item.id === savedCase)) {
    return savedCase;
  }
  return CAE_CASES[0].id;
}

function statusTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (["complete", "connected", "ready"].includes(normalized)) {
    return "text-emerald-700 bg-emerald-50 border-emerald-200";
  }
  if (["blocked", "failed", "error"].includes(normalized)) {
    return "text-red-700 bg-red-50 border-red-200";
  }
  if (["running", "building"].includes(normalized)) {
    return "text-sky-700 bg-sky-50 border-sky-200";
  }
  return "text-zinc-700 bg-zinc-50 border-zinc-200";
}

function normalizeLocale(value) {
  return value === "en" ? "en" : "zh";
}

function statusLabel(status, text) {
  const normalized = String(status || "").trim().toLowerCase();
  return text.status[normalized] || status || "";
}

function metricLabel(label, text) {
  return text.metricLabels[label] || label;
}

function workflowCopy(item, text) {
  const copy = text.workflow[item?.step];
  return {
    step: copy?.step || item?.step || "",
    detail: copy?.detail || item?.detail || "",
  };
}

function connectionMessage(message, text) {
  return text.connectionMessages[message] || message;
}

function formatValue(metric, text) {
  if (metric?.value === null || metric?.value === undefined) {
    return text.pending;
  }
  return `${metric.value} ${metric.unit || ""}`.trim();
}

function inputRows(project, text) {
  const summary = project?.inputs?.summary;
  if (Array.isArray(summary) && summary.length > 0) {
    return summary.map((item) => ({
      label: item.label?.[text === CAE_TEXT.zh ? "zh" : "en"] || item.label || "",
      value: item.value?.[text === CAE_TEXT.zh ? "zh" : "en"] || item.value || "",
    }));
  }
  return [
    {
      label: text.inputLabels.geometry,
      value: `${project?.inputs?.geometry?.length_mm || "-"} x ${project?.inputs?.geometry?.width_mm || "-"} x ${project?.inputs?.geometry?.height_mm || project?.inputs?.geometry?.thickness_mm || "-"} mm`,
    },
    {
      label: text.inputLabels.material,
      value: `${project?.inputs?.material?.name || "-"}, E = ${project?.inputs?.material?.youngs_modulus_mpa || "-"} MPa`,
    },
    {
      label: text.inputLabels.boundaryLoad,
      value: project?.inputs?.loads?.description || `${project?.inputs?.loads?.fixed_end || "-"}; Fy = ${project?.inputs?.loads?.tip_force_n || "-"} N`,
    },
    {
      label: text.inputLabels.mesh,
      value: `${project?.inputs?.mesh?.element_family || "-"}, seed ${project?.inputs?.mesh?.seed_size_mm || "-"} mm`,
    },
  ];
}

function CaeStatusIcon({ status }) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "complete" || normalized === "connected" || normalized === "ready") {
    return <CheckCircle2 className="size-4" aria-hidden="true" />;
  }
  if (normalized === "running" || normalized === "building") {
    return <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />;
  }
  return <AlertTriangle className="size-4" aria-hidden="true" />;
}

function TreeRow({ depth = 0, label, open = false, selected = false, hasChildren = false, onSelect, onToggle }) {
  return (
    <div
      className={`flex h-5 w-full items-center gap-1 whitespace-nowrap text-[11px] leading-none ${selected ? "bg-[#9fbfe0]" : "hover:bg-[#d2dce8]"}`}
      style={{ paddingLeft: `${depth * 12 + 6}px` }}
      title={label}
    >
      <button
        type="button"
        className={`flex w-2 items-center justify-center text-[9px] text-slate-700 ${hasChildren ? "cursor-pointer" : "cursor-default"}`}
        aria-label={hasChildren ? (open ? `Collapse ${label}` : `Expand ${label}`) : undefined}
        tabIndex={hasChildren ? 0 : -1}
        disabled={!hasChildren}
        onClick={onToggle}
      >
        {hasChildren ? (open ? "\u25be" : "\u25b8") : ""}
      </button>
      <button type="button" className="flex min-w-0 flex-1 items-center gap-1 text-left" onClick={onSelect}>
        <span className="size-3 shrink-0 border border-[#586f87] bg-[#f4cf63] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.45)]" />
        <span className="min-w-0 truncate">{label}</span>
      </button>
    </div>
  );
}

function CaeTreeNode({ node, depth = 0, openNodes, selectedNodeId, onToggle, onSelect }) {
  const hasChildren = Array.isArray(node.children) && node.children.length > 0;
  const open = openNodes.has(node.id);

  return (
    <div>
      <TreeRow
        depth={depth}
        label={node.label}
        open={open}
        selected={selectedNodeId === node.id}
        hasChildren={hasChildren}
        onToggle={() => onToggle(node.id)}
        onSelect={() => onSelect(node)}
      />
      {hasChildren && open ? (
        <div>
          {node.children.map((child) => (
            <CaeTreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              openNodes={openNodes}
              selectedNodeId={selectedNodeId}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function MiniHistoryChart({ series, valueKey = "maxMises", color = "#ef4444" }) {
  const points = Array.isArray(series) ? series.filter((item) => Number.isFinite(Number(item?.[valueKey]))) : [];
  if (points.length < 2) {
    return <div className="flex h-28 items-center justify-center rounded-sm border border-[#a8b7c7] bg-white/60 text-[11px] text-slate-500">No curve data</div>;
  }
  const values = points.map((item) => Number(item[valueKey]));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const valueRange = Math.max(maxValue - minValue, 1e-9);
  const width = 260;
  const height = 112;
  const padding = 14;
  const polyline = points.map((item, index) => {
    const x = padding + (index / Math.max(points.length - 1, 1)) * (width - padding * 2);
    const y = height - padding - ((Number(item[valueKey]) - minValue) / valueRange) * (height - padding * 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  return (
    <div className="rounded-sm border border-[#a8b7c7] bg-white/70 p-1">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-28 w-full" role="img" aria-label="history output chart">
        <rect x="0" y="0" width={width} height={height} fill="#f8fafc" />
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#64748b" strokeWidth="1" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="#64748b" strokeWidth="1" />
        <polyline fill="none" stroke={color} strokeWidth="2" points={polyline} />
        <text x={padding + 2} y={padding + 8} fill="#334155" fontSize="9">{maxValue.toPrecision(4)}</text>
        <text x={padding + 2} y={height - padding - 3} fill="#334155" fontSize="9">{minValue.toPrecision(4)}</text>
      </svg>
    </div>
  );
}

function historyValueForNode(nodeId) {
  if (nodeId === "history-displacement") {
    return { key: "maxDisplacement", label: "U max", color: "#2563eb" };
  }
  if (nodeId === "history-tool-position") {
    return { key: "toolX", label: "Tool X", color: "#0f766e" };
  }
  if (nodeId === "history-contact-indentation") {
    return { key: "indentationMm", label: "Indentation", color: "#7c3aed" };
  }
  if (nodeId === "history-contact-radius") {
    return { key: "contactRadiusMm", label: "Contact radius", color: "#0891b2" };
  }
  return { key: "maxMises", label: "S, Mises max", color: "#ef4444" };
}

function TreeResultInspector({ node, project, resultSummary, locale, text }) {
  const metrics = Array.isArray(project?.outputs?.metrics) ? project.outputs.metrics : [];
  const nodeId = node?.id || "";
  const historyConfig = historyValueForNode(nodeId);
  const history = Array.isArray(resultSummary?.history) ? resultSummary.history : [];
  const showChart = nodeId.startsWith("history-") || nodeId === "result-main" || nodeId === "field-stress" || nodeId === "field-displacement";
  const rows = [];
  if (nodeId.includes("mesh")) {
    rows.push(["Nodes", resultSummary?.nodeCount || "-"]);
    rows.push(["Elements", resultSummary?.elementCount || "-"]);
    rows.push(["Element type", resultSummary?.elementType || project?.inputs?.mesh?.element_family || "-"]);
  } else if (nodeId.includes("material")) {
    const material = project?.inputs?.material || {};
    rows.push(["Material", material.name || "-"]);
    rows.push(["E", `${material.youngs_modulus_mpa || "-"} MPa`]);
    rows.push(["nu", material.poissons_ratio || "-"]);
  } else if (nodeId.includes("job") || nodeId.includes("result") || nodeId.startsWith("history-") || nodeId.startsWith("field-")) {
    rows.push(["ODB", project?.outputs?.odb?.split("/").pop() || resultSummary?.source || "-"]);
    rows.push(["Step", resultSummary?.step || "-"]);
    rows.push(["Frames", resultSummary?.frameCount || "-"]);
    rows.push(["Peak S, Mises", `${Number(resultSummary?.fieldRanges?.misesMax || 0).toPrecision(5)} MPa`]);
    rows.push(["Max U", `${Number(resultSummary?.fieldRanges?.maxDisplacement || 0).toPrecision(5)} mm`]);
  } else {
    rows.push(["Item", node?.label || "-"]);
    rows.push(["Detail", node?.detail || "-"]);
  }
  return (
    <section className="space-y-2 rounded-sm border border-[#a8b7c7] bg-[#eef4fb] p-2">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-600">{text.selectedTreeTitle}</p>
        <p className="mt-0.5 truncate text-xs font-semibold text-slate-950">{node?.label || "-"}</p>
        <p className="truncate text-[11px] text-slate-600">{node?.detail || "-"}</p>
      </div>
      <div className="grid gap-1">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3 rounded-sm bg-white/65 px-2 py-1 text-[11px]">
            <span className="text-slate-500">{label}</span>
            <span className="min-w-0 truncate font-semibold text-slate-900">{value}</span>
          </div>
        ))}
      </div>
      {showChart ? (
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-semibold">{nodeId.startsWith("history-") ? text.historyOutputTitle : text.fieldOutputTitle}</p>
            <span className="text-[10px] text-slate-500">{historyConfig.label}</span>
          </div>
          {history.length > 1 ? (
            <MiniHistoryChart series={history} valueKey={historyConfig.key} color={historyConfig.color} />
          ) : (
            <p className="rounded-sm border border-[#a8b7c7] bg-white/60 p-2 text-[11px] text-slate-600">{text.noHistoryData}</p>
          )}
        </div>
      ) : null}
      {metrics.length > 0 && (nodeId.includes("result") || nodeId.includes("job")) ? (
        <div className="grid gap-1">
          {metrics.slice(0, 3).map((metric) => (
            <div key={metric.label} className="flex items-center justify-between gap-2 rounded-sm bg-white/65 px-2 py-1 text-[11px]">
              <span className="truncate text-slate-500">{metricLabel(metric.label, text)}</span>
              <span className="font-semibold">{formatValue(metric, text)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function CaeModelTree({ project, locale, selectedCaseId, cases, onCaseChange, onNodeSelect, resultSummary }) {
  const text = CAE_TEXT[locale] || CAE_TEXT.zh;
  const [openNodeIds, setOpenNodeIds] = useState(() => new Set([
    "root",
    "projects",
    "model",
    "parts",
    "materials",
    "assembly",
    "steps",
    "loads",
    "bcs",
    "mesh",
    "jobs",
    "results",
    "field-output",
    "history-output",
  ]));
  const [selectedNode, setSelectedNode] = useState(null);
  const geometry = project?.inputs?.geometry || {};
  const material = project?.inputs?.material || {};
  const mesh = project?.inputs?.mesh || {};
  const jobName = project?.outputs?.job_name || project?.project?.name || "TextToCAE";
  const odbName = project?.outputs?.odb?.split("/").pop() || `${jobName}.odb`;
  const isHolePlate = selectedCaseId === "hole-plate" || selectedCaseId === "hole-plate-modal";
  const isImpact = selectedCaseId === "sphere-impact";
  const isMilling = selectedCaseId === "milling-3d";
  const isModal = selectedCaseId === "hole-plate-modal";
  const partName = isMilling ? "Workpiece" : isImpact ? "ImpactPlate" : isHolePlate ? "HolePlate" : "CantileverBeam";
  const instanceName = isMilling ? "Workpiece-1" : isImpact ? "Plate-1" : isHolePlate ? "HolePlate-1" : "Beam-1";
  const loadName = isMilling ? "Tooth_Resolved_Milling_Load" : isImpact ? "SphereImpactEquivalent" : isModal ? "No external load" : isHolePlate ? "Right_Displacement_X" : "Tip_Load_Y";
  const bcName = isMilling ? "Fixture" : isImpact ? "Clamped_Edges" : isHolePlate ? "Fixed_Left" : "Fixed_End";
  const dimensions = isMilling
    ? `${geometry.workpiece_length_mm || "-"} x ${geometry.workpiece_width_mm || "-"} x ${geometry.workpiece_thickness_mm || "-"} mm`
    : isImpact
    ? `${geometry.length_mm || "-"} x ${geometry.width_mm || "-"} x ${geometry.thickness_mm || "-"} mm`
    : isHolePlate
    ? `${geometry.length_mm || "-"} x ${geometry.width_mm || "-"} x ${geometry.thickness_mm || "-"} mm`
    : `${geometry.length_mm || "-"} x ${geometry.width_mm || "-"} x ${geometry.height_mm || "-"} mm`;
  const tree = {
    id: "root",
    label: text.modelTreeRoot,
    detail: project?.project?.name || "TextToCAE",
    children: [
      {
        id: "projects",
        label: text.projectTreeTitle,
        detail: selectedCaseId,
        children: (cases || []).map((item) => ({
          id: `case-${item.id}`,
          caseId: item.id,
          label: `${selectedCaseId === item.id ? "\u25cf " : ""}${item.labels?.[locale] || item.id}`,
          detail: item.directory,
        })),
      },
      {
        id: "model",
        label: `${text.modelTreeModel}: ${project?.project?.model || "Model-1"}`,
        detail: project?.project?.solver || "Abaqus/CAE",
        children: [
          {
            id: "parts",
            label: text.modelTreeParts,
            detail: isMilling ? "3D deformable solid workpiece with animated end mill" : isImpact ? "3D deformable shell impact plate" : isHolePlate ? "3D deformable solid plate" : "3D deformable beam",
            children: [{ id: "part-main", label: `${partName} (${dimensions})`, detail: dimensions }],
          },
          {
            id: "materials",
            label: text.modelTreeMaterials,
            detail: `${material.name || "Steel"}, E=${material.youngs_modulus_mpa || "-"} MPa`,
            children: [{ id: "material-main", label: `${material.name || "Steel"} E=${material.youngs_modulus_mpa || "-"} MPa`, detail: `nu=${material.poissons_ratio || "-"}` }],
          },
          {
            id: "assembly",
            label: text.modelTreeAssembly,
            detail: "Root assembly",
            children: [{ id: "instance-main", label: instanceName, detail: partName }],
          },
          {
            id: "steps",
            label: text.modelTreeSteps,
            detail: isMilling || isImpact ? "Explicit dynamic" : isModal ? "Frequency extraction" : "Static general",
            children: [
              { id: "step-initial", label: "Initial", detail: "Initial boundary state" },
              { id: "step-load", label: isMilling ? "Milling" : isImpact ? "Impact" : isModal ? "Modal" : "Load", detail: isMilling ? "Transient 3D end-milling response" : isImpact ? "Transient explicit impact response" : isModal ? "Extract first natural frequencies" : "Static load/displacement step" },
            ],
          },
          { id: "interactions", label: text.modelTreeInteractions, detail: isMilling ? "Rotating multi-flute tool overlay with tooth passing load field" : isImpact ? "Equivalent sphere impact pulse" : "No contact interactions defined" },
          {
            id: "loads",
            label: text.modelTreeLoads,
            detail: project?.inputs?.loads?.description || loadName,
            children: isModal ? [] : [{ id: "load-main", label: loadName, detail: project?.inputs?.loads?.description || "" }],
          },
          {
            id: "bcs",
            label: text.modelTreeBcs,
            detail: bcName,
            children: [{ id: "bc-main", label: bcName, detail: "Constrained set" }],
          },
          {
            id: "mesh",
            label: text.modelTreeMesh,
            detail: `${mesh.element_family || "C3D"} seed ${mesh.seed_size_mm || "-"} mm`,
            children: [{ id: "mesh-main", label: `${mesh.element_family || "C3D"} seed ${mesh.seed_size_mm || "-"} mm`, detail: "Generated Abaqus mesh" }],
          },
          {
            id: "jobs",
            label: text.modelTreeJobs,
            detail: jobName,
            children: [{ id: "job-main", label: jobName, detail: project?.outputs?.status || "" }],
          },
          {
            id: "results",
            label: text.modelTreeResults,
            detail: odbName,
            children: [
              { id: "result-main", label: odbName, detail: isMilling ? "Transient milling S, Mises and U field output" : isImpact ? "Transient S, Mises and U field output" : isModal ? "Frequencies and U mode-shape field output" : "S, Mises and U field output" },
              {
                id: "field-output",
                label: "Field Output",
                detail: "Frame field values",
                children: [
                  { id: "field-stress", label: "S, Mises", detail: "Element von Mises stress contour" },
                  { id: "field-displacement", label: "U", detail: "Nodal displacement magnitude" },
                ],
              },
              {
                id: "history-output",
                label: "History Output",
                detail: `${resultSummary?.frameCount || "-"} frames`,
                children: [
                  { id: "history-stress", label: "S, Mises max for Model", detail: "Peak stress over displayed frames" },
                  { id: "history-displacement", label: "U max for Model", detail: "Maximum displacement over displayed frames" },
                  ...(isMilling ? [{ id: "history-tool-position", label: "Tool path X for Tool", detail: "Cutter position over time" }] : []),
                  ...(isImpact ? [
                    { id: "history-contact-indentation", label: "Contact indentation", detail: "Sphere indentation over time" },
                    { id: "history-contact-radius", label: "Contact radius", detail: "Sphere contact radius over time" },
                  ] : []),
                ],
              },
            ],
          },
        ],
      },
    ],
  };

  const activeNode = selectedNode || tree.children[0];
  useEffect(() => {
    setSelectedNode(null);
    onNodeSelect?.(null);
  }, [selectedCaseId]);

  const selectNode = (node) => {
    setSelectedNode(node);
    onNodeSelect?.(node);
    if (node?.caseId && node.caseId !== selectedCaseId) {
      onCaseChange?.(node.caseId);
    }
  };

  const toggleNode = (nodeId) => {
    setOpenNodeIds((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  return (
    <div className="h-full overflow-hidden font-sans">
      <div className="border-b border-[#9aabba] bg-[#ccd8e5] px-2 py-1 text-[12px] font-semibold text-slate-950">
        {text.modelTreeTitle}
      </div>
      <div className="flex h-[calc(100%-1.75rem)] flex-col">
        <div className="min-h-0 flex-1 overflow-auto py-1">
          <CaeTreeNode
            node={tree}
            openNodes={openNodeIds}
            selectedNodeId={activeNode.id}
            onToggle={toggleNode}
            onSelect={selectNode}
          />
        </div>
        <div className="border-t border-[#9aabba] bg-[#d7e2ee] px-2 py-1 text-[10px] leading-4 text-slate-700">
          <p className="truncate font-semibold text-slate-900">{activeNode.label}</p>
          <p className="truncate">{activeNode.detail || "-"}</p>
        </div>
      </div>
    </div>
  );
}

export default function TextToCaeWorkspace() {
  const [selectedCaseId, setSelectedCaseId] = useState(getInitialCaseId);
  const [project, setProject] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [copyStatus, setCopyStatus] = useState("");
  const [parameterPayload, setParameterPayload] = useState(null);
  const [parameterDraft, setParameterDraft] = useState({});
  const [parameterError, setParameterError] = useState("");
  const [runMessage, setRunMessage] = useState("");
  const [runningSimulation, setRunningSimulation] = useState(false);
  const [resultVersion, setResultVersion] = useState(0);
  const [resultSummary, setResultSummary] = useState(null);
  const [selectedTreeNode, setSelectedTreeNode] = useState(null);
  const [locale, setLocale] = useState(() => {
    if (typeof window === "undefined") {
      return "zh";
    }
    return normalizeLocale(window.localStorage.getItem("text-to-cae-language") || "zh");
  });

  const text = CAE_TEXT[locale] || CAE_TEXT.zh;
  const selectedCase = CAE_CASES.find((item) => item.id === selectedCaseId) || CAE_CASES[0];
  const caeDirectory = selectedCase.directory;

  const loadProject = async () => {
    setLoading(true);
    setError("");
    try {
      setProject(await fetchCaeProject(caeDirectory));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      setProject(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProject();
  }, [caeDirectory]);

  useEffect(() => {
    let cancelled = false;
    setResultSummary(null);
    fetchCaeResultSummary(caeDirectory)
      .then((summary) => {
        if (!cancelled) {
          setResultSummary(summary);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResultSummary(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [caeDirectory, resultVersion]);

  useEffect(() => {
    let cancelled = false;
    setParameterPayload(null);
    setParameterDraft({});
    setParameterError("");
    setRunMessage("");
    fetchCaeParameters(caeDirectory)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setParameterPayload(payload);
        setParameterDraft(payload?.parameters || {});
      })
      .catch((loadError) => {
        if (!cancelled) {
          setParameterError(loadError instanceof Error ? loadError.message : String(loadError));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [caeDirectory]);

  const metrics = useMemo(() => (
    Array.isArray(project?.outputs?.metrics) ? project.outputs.metrics : []
  ), [project]);

  const workflow = useMemo(() => (
    Array.isArray(project?.workflow) ? project.workflow : []
  ), [project]);

  const connectionStatus = project?.connection?.status || "loading";
  const outputStatus = project?.outputs?.status || "loading";
  const runCommand = selectedCase.id === "f22-flow"
    ? `fluent 3ddp -g -i ${project?.project?.source || `${caeDirectory}/f22_external_flow_fluent.jou`}`
    : `abaqus cae noGUI=${project?.project?.source || `${caeDirectory}/run_abaqus.py`}`;
  const gearParameterKeys = ["module_mm", "driver_teeth", "driven_teeth", "face_width_mm", "driver_speed_rpm", "transmitted_torque_nmm", "pressure_angle_deg", "backlash_mm", "step_time_s", "output_frames", "seed_size_mm", "youngs_modulus_mpa", "poissons_ratio"];
  const f22ParameterKeys = ["length_m", "wingspan_m", "mach", "altitude_m", "angle_of_attack_deg", "sideslip_deg", "reference_area_m2", "dynamic_pressure_pa"];
  const visibleParameterFields = selectedCase.id === "sphere-impact"
    ? PARAMETER_FIELDS.filter((field) => !["hole_radius_mm", "right_displacement_x_mm", "workpiece_length_mm", "workpiece_width_mm", "workpiece_thickness_mm", "tool_diameter_mm", "flute_count", "spindle_speed_rpm", "feed_per_tooth_mm", "axial_depth_mm", "radial_width_mm", "step_time_s", "output_frames", ...gearParameterKeys, ...f22ParameterKeys].includes(field.key))
    : selectedCase.id === "milling-3d"
      ? PARAMETER_FIELDS.filter((field) => ["workpiece_length_mm", "workpiece_width_mm", "workpiece_thickness_mm", "tool_diameter_mm", "flute_count", "spindle_speed_rpm", "feed_per_tooth_mm", "axial_depth_mm", "radial_width_mm", "step_time_s", "output_frames", "seed_size_mm", "youngs_modulus_mpa", "poissons_ratio"].includes(field.key))
    : selectedCase.id === "gear-mesh"
      ? PARAMETER_FIELDS.filter((field) => gearParameterKeys.includes(field.key))
    : selectedCase.id === "f22-flow"
      ? PARAMETER_FIELDS.filter((field) => f22ParameterKeys.includes(field.key))
    : selectedCase.id === "hole-plate-modal"
      ? PARAMETER_FIELDS.filter((field) => !["right_displacement_x_mm", "ball_radius_mm", "impact_velocity_mps", "workpiece_length_mm", "workpiece_width_mm", "workpiece_thickness_mm", "tool_diameter_mm", "flute_count", "spindle_speed_rpm", "feed_per_tooth_mm", "axial_depth_mm", "radial_width_mm", "step_time_s", "output_frames", ...gearParameterKeys, ...f22ParameterKeys].includes(field.key))
      : PARAMETER_FIELDS.filter((field) => !["ball_radius_mm", "impact_velocity_mps", "workpiece_length_mm", "workpiece_width_mm", "workpiece_thickness_mm", "tool_diameter_mm", "flute_count", "spindle_speed_rpm", "feed_per_tooth_mm", "axial_depth_mm", "radial_width_mm", "step_time_s", "output_frames", ...gearParameterKeys, ...f22ParameterKeys].includes(field.key));

  const copyRunCommand = async () => {
    try {
      await navigator.clipboard.writeText(runCommand);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
  };

  const handleParameterChange = (key, value) => {
    setParameterDraft((current) => ({
      ...current,
      [key]: value,
    }));
    setRunMessage("");
    setParameterError("");
  };

  const handleRunSimulation = async () => {
    setRunningSimulation(true);
    setRunMessage(text.runningSimulation);
    setParameterError("");
    setError("");
    try {
      const payload = await runCaeSimulation(caeDirectory, parameterDraft);
      setParameterPayload((current) => ({
        ...(current || {}),
        editable: true,
        parameters: payload.parameters || parameterDraft,
      }));
      setParameterDraft(payload.parameters || parameterDraft);
      setProject(payload.project || await fetchCaeProject(caeDirectory));
      setResultVersion((version) => version + 1);
      setRunMessage(text.runComplete);
    } catch (runError) {
      const message = runError instanceof Error ? runError.message : String(runError);
      setParameterError(message);
      setRunMessage(`${text.runFailed}: ${message}`);
      await loadProject();
    } finally {
      setRunningSimulation(false);
    }
  };

  const handleLanguageChange = (nextLocale) => {
    const normalized = normalizeLocale(nextLocale);
    setLocale(normalized);
    setCopyStatus("");
    if (typeof window !== "undefined") {
      window.localStorage.setItem("text-to-cae-language", normalized);
    }
  };

  const handleCaseChange = (nextCaseId) => {
    const nextCase = CAE_CASES.find((item) => item.id === nextCaseId) || CAE_CASES[0];
    setSelectedCaseId(nextCase.id);
    setCopyStatus("");
    setSelectedTreeNode(null);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("text-to-cae-case", nextCase.id);
      const url = new URL(window.location.href);
      url.searchParams.set("mode", "cae");
      url.searchParams.set("case", nextCase.id);
      url.searchParams.delete("caeDir");
      window.history.replaceState(null, "", url.toString());
    }
  };

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const url = new URL(window.location.href);
    const urlCase = url.searchParams.get("case");
    const urlDir = url.searchParams.get("caeDir");
    const validUrlCase = !urlCase || CAE_CASES.some((item) => item.id === urlCase);
    const validUrlDir = !urlDir || CAE_CASES.some((item) => item.directory === urlDir);
    if (validUrlCase && validUrlDir) {
      return;
    }
    window.localStorage.setItem("text-to-cae-case", selectedCase.id);
    url.searchParams.set("case", selectedCase.id);
    url.searchParams.delete("caeDir");
    window.history.replaceState(null, "", url.toString());
  }, [selectedCase.id]);

  const inspectorPanel = (
    <div className="flex h-full flex-col overflow-hidden text-slate-950">
      <div className="shrink-0 border-b border-[#a8b7c7] bg-[#ccd8e5] px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{project?.project?.name || text.loadingProject}</p>
            <p className="truncate text-[10px] text-slate-600">{project?.project?.model || text.modelFallback}</p>
          </div>
          <div className="inline-flex overflow-hidden rounded-sm border border-[#91a4b8] bg-white text-[10px] font-semibold" aria-label={text.languageLabel}>
            <button
              type="button"
              className={`px-1.5 py-1 ${locale === "zh" ? "bg-[#244b73] text-white" : "text-slate-700 hover:bg-slate-100"}`}
              aria-pressed={locale === "zh"}
              onClick={() => handleLanguageChange("zh")}
            >
              {text.chinese}
            </button>
            <button
              type="button"
              className={`px-1.5 py-1 ${locale === "en" ? "bg-[#244b73] text-white" : "text-slate-700 hover:bg-slate-100"}`}
              aria-pressed={locale === "en"}
              onClick={() => handleLanguageChange("en")}
            >
              {text.english}
            </button>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          <span className={`inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[10px] font-semibold ${statusTone(outputStatus)}`}>
            <CaeStatusIcon status={outputStatus} />
            {statusLabel(outputStatus, text)}
          </span>
          <span className={`inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[10px] font-semibold ${statusTone(connectionStatus)}`}>
            <CaeStatusIcon status={connectionStatus} />
            {statusLabel(connectionStatus, text)}
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {error ? (
          <div className="rounded-sm border border-red-300 bg-red-50 p-2 text-xs text-red-800">
            <p className="font-semibold">{text.loadErrorTitle}</p>
            <p>{error}</p>
          </div>
        ) : null}

        {selectedTreeNode ? (
          <TreeResultInspector
            node={selectedTreeNode}
            project={project}
            resultSummary={resultSummary}
            locale={locale}
            text={text}
          />
        ) : null}

        <section className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-xs font-semibold">{text.metricsTitle}</h3>
            <Button type="button" variant="outline" size="sm" className="h-7 rounded-sm px-2 text-[11px]" onClick={() => void loadProject()} disabled={loading}>
              <RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
              {text.refresh}
            </Button>
          </div>
          <div className="grid gap-2">
            {metrics.map((metric) => (
              <div key={metric.label} className="rounded-sm border border-[#a8b7c7] bg-white/70 p-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="min-w-0 truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-600">{metricLabel(metric.label, text)}</p>
                  <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${statusTone(metric.state)}`}>
                    {statusLabel(metric.state, text)}
                  </span>
                </div>
                <p className="mt-1 text-lg font-semibold tabular-nums">{formatValue(metric, text)}</p>
              </div>
            ))}
          </div>
        </section>

        {parameterPayload?.editable ? (
          <section className="space-y-2 border-t border-[#a8b7c7] pt-3">
            <div className="flex items-center gap-2">
              <RefreshCw className={`size-4 text-slate-600 ${runningSimulation ? "animate-spin" : ""}`} aria-hidden="true" />
              <h3 className="text-xs font-semibold">{text.parametersTitle}</h3>
            </div>
            <div className="grid gap-2">
              {visibleParameterFields.map((field) => (
                <label key={field.key} className="grid gap-1 text-[11px] font-medium text-slate-700">
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate">{field.labels[locale]}</span>
                    <span className="text-[10px] text-slate-500">{field.unit}</span>
                  </span>
                  <input
                    className="h-7 rounded-sm border border-[#91a4b8] bg-white px-2 text-xs text-slate-950 outline-none transition focus:border-[#2b5f95] focus:ring-2 focus:ring-[#7da6cf]/45 disabled:bg-slate-100"
                    type="number"
                    min={field.min}
                    max={field.max}
                    step={field.step}
                    value={parameterDraft[field.key] ?? ""}
                    disabled={runningSimulation}
                    onChange={(event) => handleParameterChange(field.key, event.target.value)}
                  />
                </label>
              ))}
            </div>
            <Button
              type="button"
              className="h-8 w-full rounded-sm text-xs"
              onClick={() => void handleRunSimulation()}
              disabled={runningSimulation}
            >
              <RefreshCw className={`size-3.5 ${runningSimulation ? "animate-spin" : ""}`} aria-hidden="true" />
              {runningSimulation ? text.runningSimulation : text.runSimulation}
            </Button>
            {runMessage || parameterError ? (
              <p className={`text-[11px] leading-4 ${parameterError ? "text-red-700" : "text-slate-600"}`}>
                {runMessage || parameterError}
              </p>
            ) : null}
          </section>
        ) : null}

        <section className="space-y-2 border-t border-[#a8b7c7] pt-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-xs font-semibold">{text.commandTitle}</h3>
            <Button type="button" size="sm" className="h-7 rounded-sm px-2 text-[11px]" title={text.copyTitle} onClick={() => void copyRunCommand()}>
              <Copy className="size-3" aria-hidden="true" />
              {copyStatus === "copied" ? text.copied : copyStatus === "failed" ? text.copyFailed : text.copyCommand}
            </Button>
          </div>
          <div className="rounded-sm border border-[#1f2937] bg-zinc-950 px-2 py-2 font-mono text-[10px] leading-4 text-zinc-100">
            {runCommand}
          </div>
        </section>

        <section className="space-y-2 border-t border-[#a8b7c7] pt-3">
          <div className="flex items-center gap-2">
            <TerminalSquare className="size-4 text-slate-600" aria-hidden="true" />
            <h3 className="text-xs font-semibold">{text.workflowTitle}</h3>
          </div>
          <div className="divide-y divide-[#a8b7c7] rounded-sm border border-[#a8b7c7] bg-white/60">
            {workflow.map((item) => (
              <div key={item.step} className="p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1 text-[11px] font-semibold">
                    <CaeStatusIcon status={item.status} />
                    {workflowCopy(item, text).step}
                  </span>
                  <span className={`rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${statusTone(item.status)}`}>
                    {statusLabel(item.status, text)}
                  </span>
                </div>
                <p className="mt-1 text-[11px] leading-4 text-slate-600">{workflowCopy(item, text).detail}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );

  return (
    <div className="h-svh overflow-hidden bg-zinc-950 p-2 text-zinc-950">
      <CaeResultViewer
        key={`${caeDirectory}:${resultVersion}`}
        project={project}
        locale={locale}
        caeDirectory={caeDirectory}
        fullViewport
        leftPanel={(
          <CaeModelTree
            project={project}
            locale={locale}
            selectedCaseId={selectedCase.id}
            cases={CAE_CASES}
            onCaseChange={handleCaseChange}
            onNodeSelect={setSelectedTreeNode}
            resultSummary={resultSummary}
          />
        )}
        leftPanelTitle={text.modelTreeTitle}
        rightPanel={inspectorPanel}
        rightPanelTitle={text.parametersTitle}
      />
    </div>
  );
}
