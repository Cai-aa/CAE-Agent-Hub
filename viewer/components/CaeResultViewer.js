import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, RotateCcw } from "lucide-react";
import * as THREE from "three";
import { fetchCaeResultMesh } from "../lib/caeProjectStore";

const VIEWPORT_THEMES = Object.freeze({
  abaqus: {
    id: "abaqus",
    label: "Abaqus",
    background: 0x203750,
    cssBackground: "linear-gradient(180deg, #1f344e 0%, #263f5b 55%, #a8b7c9 100%)",
    border: "#182b42",
    header: "#1f344e",
    text: "#ffffff",
  },
  dark: {
    id: "dark",
    label: "Dark",
    background: 0x08243d,
    cssBackground: "#08243d",
    border: "#1d4ed8",
    header: "#1e3a8a",
    text: "#ffffff",
  },
  light: {
    id: "light",
    label: "Light",
    background: 0xf8fafc,
    cssBackground: "#f8fafc",
    border: "#cbd5e1",
    header: "#e2e8f0",
    text: "#0f172a",
  },
});

const VIEWER_TEXT = Object.freeze({
  en: {
    titlePrefix: "Text-to-CAE Result - ODB:",
    themeLabels: {
      abaqus: "Abaqus",
      dark: "Dark",
      light: "Light",
    },
    loading: "Loading Abaqus ODB mesh...",
    collapsePanel: "Collapse panel",
    expandPanel: "Expand panel",
    modeSelectorLabel: "Mode shapes",
    timeSelectorLabel: "Time frames",
    play: "Play",
    pause: "Pause",
    resetPlayback: "Reset",
    speedLabel: "Speed",
    legendTitle: "S, Mises",
    modalFooterStep: "Step: Modal | Mode",
    modalFooterFrequency: "frequency",
    modalFooterPrimary: "Primary Var: U, Magnitude | Deformed Var: U, scale",
    dynamicFooterStep: "Step:",
    dynamicFooterTime: "Time",
    dynamicFooterPrimary: "Primary Var: S, Mises | Deformed Var: U, scale",
    footerStep: "Step: Load | Primary Var: S, Mises | Deformed Var: U, scale",
    footerMesh: "nodes |",
    footerElements: "elements | Left drag rotates. Middle drag pans. Mouse wheel zooms.",
  },
  zh: {
    titlePrefix: "\u6587\u672c\u5230 CAE \u7ed3\u679c - ODB:",
    themeLabels: {
      abaqus: "Abaqus",
      dark: "\u6df1\u8272",
      light: "\u6d45\u8272",
    },
    loading: "\u6b63\u5728\u52a0\u8f7d Abaqus ODB \u7f51\u683c...",
    collapsePanel: "\u6536\u8d77\u9762\u677f",
    expandPanel: "\u5c55\u5f00\u9762\u677f",
    modeSelectorLabel: "\u6a21\u6001\u632f\u578b",
    timeSelectorLabel: "\u65f6\u95f4\u5e27",
    play: "\u64ad\u653e",
    pause: "\u6682\u505c",
    resetPlayback: "\u56de\u5230\u9996\u5e27",
    speedLabel: "\u901f\u5ea6",
    legendTitle: "S, Mises",
    modalFooterStep: "\u5206\u6790\u6b65\uff1aModal | \u6a21\u6001",
    modalFooterFrequency: "\u9891\u7387",
    modalFooterPrimary: "\u4e3b\u53d8\u91cf\uff1aU, Magnitude | \u53d8\u5f62\u53d8\u91cf\uff1aU\uff0c\u6bd4\u4f8b",
    dynamicFooterStep: "\u5206\u6790\u6b65\uff1a",
    dynamicFooterTime: "\u65f6\u95f4",
    dynamicFooterPrimary: "\u4e3b\u53d8\u91cf\uff1aS, Mises | \u53d8\u5f62\u53d8\u91cf\uff1aU\uff0c\u6bd4\u4f8b",
    footerStep: "\u5206\u6790\u6b65\uff1aLoad | \u4e3b\u53d8\u91cf\uff1aS, Mises | \u53d8\u5f62\u53d8\u91cf\uff1aU\uff0c\u6bd4\u4f8b",
    footerMesh: "\u8282\u70b9 |",
    footerElements: "\u5355\u5143 | \u5de6\u952e\u62d6\u52a8\u65cb\u8f6c\uff0c\u4e2d\u952e\u62d6\u52a8\u5e73\u79fb\uff0c\u6eda\u8f6e\u7f29\u653e\u3002",
  },
});

const HEX_FACE_NODE_INDICES = Object.freeze([
  [0, 1, 2, 3],
  [4, 7, 6, 5],
  [0, 4, 5, 1],
  [1, 5, 6, 2],
  [2, 6, 7, 3],
  [3, 7, 4, 0],
]);

const TET_FACE_NODE_INDICES = Object.freeze([
  [0, 2, 1],
  [0, 1, 3],
  [1, 2, 3],
  [2, 0, 3],
]);

const QUAD_FACE_NODE_INDICES = Object.freeze([[0, 1, 2, 3]]);
const TRI_FACE_NODE_INDICES = Object.freeze([[0, 1, 2]]);

function toFiniteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function colorForRatio(ratio) {
  const clamped = Math.min(Math.max(ratio, 0), 1);
  const color = new THREE.Color();
  color.setHSL((1 - clamped) * 0.66, 1, 0.5);
  return color;
}

function faceKey(labels) {
  return [...labels].sort((a, b) => a - b).join(":");
}

function getElementFaceNodeIndices(element) {
  const elementType = String(element?.type || "").toUpperCase();
  if (elementType.startsWith("C3D4") || elementType.startsWith("C3D10")) {
    return TET_FACE_NODE_INDICES;
  }
  if (
    elementType.startsWith("S3") ||
    elementType.startsWith("STRI3") ||
    elementType.startsWith("CPS3") ||
    elementType.startsWith("CPE3")
  ) {
    return TRI_FACE_NODE_INDICES;
  }
  if (
    elementType.startsWith("S4") ||
    elementType.startsWith("S8") ||
    elementType.startsWith("CPS4") ||
    elementType.startsWith("CPE4") ||
    elementType.startsWith("M3D4")
  ) {
    return QUAD_FACE_NODE_INDICES;
  }
  return HEX_FACE_NODE_INDICES;
}

function gridSubdivisionCount(mesh) {
  const configured = Number(mesh?.visual?.surfaceGridSubdivisions ?? mesh?.surfaceGridSubdivisions ?? 1);
  if (!Number.isFinite(configured)) {
    return 1;
  }
  return Math.min(Math.max(Math.round(configured), 1), 4);
}

function interpolateQuadPoint(points, u, v) {
  const a = (1 - u) * (1 - v);
  const b = u * (1 - v);
  const c = u * v;
  const d = (1 - u) * v;
  return [
    points[0][0] * a + points[1][0] * b + points[2][0] * c + points[3][0] * d,
    points[0][1] * a + points[1][1] * b + points[2][1] * c + points[3][1] * d,
    points[0][2] * a + points[1][2] * b + points[2][2] * c + points[3][2] * d,
  ];
}

function pushLineSegment(linePositions, start, end) {
  linePositions.push(start[0], start[1], start[2], end[0], end[1], end[2]);
}

function appendInteriorGridLines(facePoints, subdivisions, linePositions) {
  if (subdivisions <= 1 || facePoints.length !== 4) {
    return;
  }
  for (let index = 1; index < subdivisions; index += 1) {
    const t = index / subdivisions;
    pushLineSegment(linePositions, interpolateQuadPoint(facePoints, t, 0), interpolateQuadPoint(facePoints, t, 1));
    pushLineSegment(linePositions, interpolateQuadPoint(facePoints, 0, t), interpolateQuadPoint(facePoints, 1, t));
  }
}

function buildResultSurface(mesh) {
  if (mesh?.representation === "material-points") {
    const positions = [], colors = [];
    const bounds = new THREE.Box3();
    const nodes = Array.isArray(mesh.nodes) ? mesh.nodes : [];
    const min = Number(mesh.fieldRanges?.valueMin ?? 0);
    const max = Number(mesh.fieldRanges?.valueMax ?? mesh.fieldRanges?.maxDisplacement ?? 1);
    for (const node of nodes) {
      const point = node.deformed || node.coordinates;
      positions.push(...point);
      bounds.expandByPoint(new THREE.Vector3(...point));
      const color = colorForRatio((Number(node.value || 0) - min) / Math.max(max - min, 1e-30));
      colors.push(color.r, color.g, color.b);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    return { bounds, surfaceGeometry: geometry, lineGeometry: new THREE.BufferGeometry(), minMises: min, maxMises: max, materialPoints: true };
  }
  const nodes = Array.isArray(mesh?.nodes) ? mesh.nodes : [];
  const elements = Array.isArray(mesh?.elements) ? mesh.elements : [];
  const nodeByLabel = new Map(nodes.map((node) => [Number(node.label), node]));
  const faces = new Map();

  for (const element of elements) {
    const connectivity = Array.isArray(element?.connectivity) ? element.connectivity.map(Number) : [];
    const faceNodeIndices = getElementFaceNodeIndices(element);
    const requiredNodeCount = Math.max(...faceNodeIndices.flat()) + 1;
    if (connectivity.length < requiredNodeCount) {
      continue;
    }
    for (const faceIndices of faceNodeIndices) {
      const labels = faceIndices.map((index) => connectivity[index]);
      const key = faceKey(labels);
      if (faces.has(key)) {
        faces.delete(key);
        continue;
      }
      faces.set(key, {
        labels,
        mises: toFiniteNumber(element.mises, 0),
        color: element.color || "",
        showEdges: element.showEdges !== false,
      });
    }
  }

  const minMises = toFiniteNumber(mesh?.fieldRanges?.misesMin, 0);
  const maxMises = toFiniteNumber(mesh?.fieldRanges?.misesMax, minMises + 1);
  const range = Math.max(maxMises - minMises, 1.0e-6);
  const surfaceGridSubdivisions = gridSubdivisionCount(mesh);
  const positions = [];
  const colors = [];
  const indices = [];
  const linePositions = [];
  const linePairs = new Set();
  const bounds = new THREE.Box3();

  for (const face of faces.values()) {
    const baseIndex = positions.length / 3;
    const ratio = (face.mises - minMises) / range;
    const color = face.color ? new THREE.Color(face.color) : colorForRatio(ratio);
    const facePoints = [];
    for (const label of face.labels) {
      const node = nodeByLabel.get(label);
      const point = Array.isArray(node?.deformed) ? node.deformed : node?.coordinates;
      const x = toFiniteNumber(point?.[0], 0);
      const y = toFiniteNumber(point?.[1], 0);
      const z = toFiniteNumber(point?.[2], 0);
      facePoints.push([x, y, z]);
      positions.push(x, y, z);
      colors.push(color.r, color.g, color.b);
      bounds.expandByPoint(new THREE.Vector3(x, y, z));
    }

    if (face.labels.length === 3) {
      indices.push(baseIndex, baseIndex + 1, baseIndex + 2);
    } else {
      indices.push(baseIndex, baseIndex + 1, baseIndex + 2, baseIndex, baseIndex + 2, baseIndex + 3);
    }

    if (face.showEdges) {
      for (let index = 0; index < face.labels.length; index += 1) {
        const aLabel = face.labels[index];
        const bLabel = face.labels[(index + 1) % face.labels.length];
        const edgeKey = faceKey([aLabel, bLabel]);
        if (linePairs.has(edgeKey)) {
          continue;
        }
        linePairs.add(edgeKey);
        const a = nodeByLabel.get(aLabel);
        const b = nodeByLabel.get(bLabel);
        const aPoint = Array.isArray(a?.deformed) ? a.deformed : a?.coordinates;
        const bPoint = Array.isArray(b?.deformed) ? b.deformed : b?.coordinates;
        linePositions.push(
          toFiniteNumber(aPoint?.[0], 0), toFiniteNumber(aPoint?.[1], 0), toFiniteNumber(aPoint?.[2], 0),
          toFiniteNumber(bPoint?.[0], 0), toFiniteNumber(bPoint?.[1], 0), toFiniteNumber(bPoint?.[2], 0),
        );
      }
      appendInteriorGridLines(facePoints, surfaceGridSubdivisions, linePositions);
    }
  }

  const surfaceGeometry = new THREE.BufferGeometry();
  surfaceGeometry.setIndex(indices);
  surfaceGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  surfaceGeometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  surfaceGeometry.computeVertexNormals();

  const lineGeometry = new THREE.BufferGeometry();
  lineGeometry.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));

  return {
    bounds,
    lineGeometry,
    maxMises,
    minMises,
    surfaceGeometry,
  };
}

function transformToolPoint(point, pose) {
  const angle = toFiniteNumber(pose?.angleRad, 0);
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const x = toFiniteNumber(point?.[0], 0);
  const y = toFiniteNumber(point?.[1], 0);
  const z = toFiniteNumber(point?.[2], 0);
  return [
    toFiniteNumber(pose?.x, 0) + x * cos - y * sin,
    toFiniteNumber(pose?.y, 0) + x * sin + y * cos,
    toFiniteNumber(pose?.z, 0) + z,
  ];
}

function buildToolSurface(toolModel, pose) {
  const nodes = Array.isArray(toolModel?.nodes) ? toolModel.nodes : [];
  const elements = Array.isArray(toolModel?.elements) ? toolModel.elements : [];
  if (!nodes.length || !elements.length || !pose) {
    return null;
  }
  const transformedByLabel = new Map();
  const bounds = new THREE.Box3();
  for (const node of nodes) {
    const point = transformToolPoint(node?.coordinates, pose);
    transformedByLabel.set(Number(node.label), point);
    bounds.expandByPoint(new THREE.Vector3(point[0], point[1], point[2]));
  }

  const positions = [];
  const colors = [];
  const indices = [];
  const linePositions = [];
  const linePairs = new Set();
  for (const element of elements) {
    const connectivity = Array.isArray(element?.connectivity) ? element.connectivity.map(Number) : [];
    if (connectivity.length < 3) {
      continue;
    }
    const baseIndex = positions.length / 3;
    const color = new THREE.Color(element.color || "#aeb7c3");
    for (const label of connectivity.slice(0, 3)) {
      const point = transformedByLabel.get(label);
      if (!point) {
        continue;
      }
      positions.push(point[0], point[1], point[2]);
      colors.push(color.r, color.g, color.b);
    }
    if (positions.length / 3 < baseIndex + 3) {
      continue;
    }
    indices.push(baseIndex, baseIndex + 1, baseIndex + 2);
    for (let index = 0; index < 3; index += 1) {
      const aLabel = connectivity[index];
      const bLabel = connectivity[(index + 1) % 3];
      const key = faceKey([aLabel, bLabel]);
      if (linePairs.has(key)) {
        continue;
      }
      linePairs.add(key);
      const a = transformedByLabel.get(aLabel);
      const b = transformedByLabel.get(bLabel);
      if (a && b) {
        linePositions.push(a[0], a[1], a[2], b[0], b[1], b[2]);
      }
    }
  }

  const surfaceGeometry = new THREE.BufferGeometry();
  surfaceGeometry.setIndex(indices);
  surfaceGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  surfaceGeometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  surfaceGeometry.computeVertexNormals();

  const lineGeometry = new THREE.BufferGeometry();
  lineGeometry.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));

  return { bounds, lineGeometry, surfaceGeometry };
}

function buildDisplayBounds(mesh, { includeVisualOnly = true } = {}) {
  const bounds = new THREE.Box3();
  const nodes = Array.isArray(mesh?.nodes) ? mesh.nodes : [];
  for (const node of nodes) {
    if (!includeVisualOnly && node?.visualOnly) {
      continue;
    }
    const point = Array.isArray(node?.deformed) ? node.deformed : node?.coordinates;
    if (!Array.isArray(point)) {
      continue;
    }
    bounds.expandByPoint(new THREE.Vector3(
      toFiniteNumber(point[0], 0),
      toFiniteNumber(point[1], 0),
      toFiniteNumber(point[2], 0),
    ));
  }
  const toolModel = mesh?.toolModel;
  const toolPose = mesh?.toolPose;
  if (toolModel && toolPose && Array.isArray(toolModel.nodes)) {
    for (const node of toolModel.nodes) {
      const point = transformToolPoint(node?.coordinates, toolPose);
      bounds.expandByPoint(new THREE.Vector3(point[0], point[1], point[2]));
    }
  }
  if (bounds.isEmpty() && !includeVisualOnly) {
    return buildDisplayBounds(mesh, { includeVisualOnly: true });
  }
  return bounds;
}

function formatLegendValue(value) {
  return `${value >= 0 ? "+" : "-"}${Math.abs(value).toExponential(3)}`;
}

export default function CaeResultViewer({
  project,
  resultMesh = null,
  locale = "zh",
  caeDirectory,
  leftPanel = null,
  leftPanelTitle = "",
  rightPanel = null,
  rightPanelTitle = "",
  fullViewport = false,
}) {
  const containerRef = useRef(null);
  const orbitStateRef = useRef(null);
  const [mesh, setMesh] = useState(null);
  const [meshError, setMeshError] = useState("");
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [selectedModeIndex, setSelectedModeIndex] = useState(0);
  const [selectedDynamicFrameIndex, setSelectedDynamicFrameIndex] = useState(0);
  const [dynamicPlaying, setDynamicPlaying] = useState(false);
  const [dynamicPlaybackSpeed, setDynamicPlaybackSpeed] = useState(1);
  const [viewportThemeId, setViewportThemeId] = useState(() => {
    if (typeof window === "undefined") {
      return "abaqus";
    }
    const saved = window.localStorage.getItem("text-to-cae-viewport-theme");
    return VIEWPORT_THEMES[saved] ? saved : "abaqus";
  });
  const viewportTheme = VIEWPORT_THEMES[viewportThemeId] || VIEWPORT_THEMES.abaqus;
  const text = VIEWER_TEXT[locale === "en" ? "en" : "zh"];
  const modalFrames = Array.isArray(mesh?.modalFrames) ? mesh.modalFrames : [];
  const dynamicFrames = Array.isArray(mesh?.dynamicFrames) ? mesh.dynamicFrames : [];
  const displayMesh = modalFrames[selectedModeIndex] ? {
    ...mesh,
    ...modalFrames[selectedModeIndex],
    analysisType: mesh?.analysisType,
    source: mesh?.source,
    step: mesh?.step,
    modalFrames,
  } : dynamicFrames[selectedDynamicFrameIndex] ? {
    ...mesh,
    ...dynamicFrames[selectedDynamicFrameIndex],
    analysisType: mesh?.analysisType,
    source: mesh?.source,
    step: mesh?.step,
    dynamicFrames,
  } : mesh;
  const elementType = displayMesh?.elementType || displayMesh?.elements?.[0]?.type || "";
  const fieldLabel = displayMesh?.fieldLabel || text.legendTitle;
  const isModalResult = displayMesh?.analysisType === "modal";
  const isDynamicResult = displayMesh?.analysisType === "dynamic";

  useEffect(() => {
    setSelectedModeIndex(0);
    setSelectedDynamicFrameIndex(0);
    setDynamicPlaying(false);
    orbitStateRef.current = null;
  }, [caeDirectory, project?.outputs?.status, resultMesh]);

  useEffect(() => {
    if (selectedModeIndex >= modalFrames.length && modalFrames.length > 0) {
      setSelectedModeIndex(0);
    }
  }, [modalFrames.length, selectedModeIndex]);

  useEffect(() => {
    if (selectedDynamicFrameIndex >= dynamicFrames.length && dynamicFrames.length > 0) {
      setSelectedDynamicFrameIndex(0);
    }
  }, [dynamicFrames.length, selectedDynamicFrameIndex]);

  useEffect(() => {
    if (!dynamicPlaying || dynamicFrames.length <= 1) {
      return undefined;
    }
    const frameDurationMs = Math.max(16, (mesh?.representation === "material-points" ? 180 : 16) / Math.max(dynamicPlaybackSpeed, 0.25));
    const intervalId = window.setInterval(() => {
      setSelectedDynamicFrameIndex((current) => (current + 1) % dynamicFrames.length);
    }, frameDurationMs);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [dynamicFrames.length, dynamicPlaybackSpeed, dynamicPlaying]);

  useEffect(() => {
    let cancelled = false;
    if (resultMesh) {
      setMesh(resultMesh);
      setMeshError("");
      return undefined;
    }
    setMesh(null);
    setMeshError("");
    fetchCaeResultMesh(caeDirectory)
      .then((payload) => {
        if (!cancelled) {
          setMesh(payload);
          setMeshError("");
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setMeshError(error instanceof Error ? error.message : String(error));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [caeDirectory, project?.outputs?.status, resultMesh]);

  const surface = useMemo(() => (displayMesh ? buildResultSurface(displayMesh) : null), [displayMesh]);
  const toolSurface = useMemo(() => (
    displayMesh?.toolModel && displayMesh?.toolPose ? buildToolSurface(displayMesh.toolModel, displayMesh.toolPose) : null
  ), [displayMesh]);
  const framingBounds = useMemo(() => {
    if (dynamicFrames.length > 0) {
      return buildDisplayBounds({ ...mesh, ...dynamicFrames[0] }, { includeVisualOnly: false });
    }
    if (modalFrames[selectedModeIndex]) {
      return buildDisplayBounds(modalFrames[selectedModeIndex], { includeVisualOnly: false });
    }
    return displayMesh ? buildDisplayBounds(displayMesh, { includeVisualOnly: false }) : null;
  }, [displayMesh, dynamicFrames, modalFrames, selectedModeIndex]);
  const legendValues = useMemo(() => {
    const minValue = surface?.minMises ?? 0;
    const maxValue = surface?.maxMises ?? 0;
    return Array.from({ length: 13 }, (_, index) => maxValue - ((maxValue - minValue) * index) / 12);
  }, [surface]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !surface) {
      return undefined;
    }

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(viewportTheme.background, 0);
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 3000);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x1f2937, 2.1));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
    keyLight.position.set(50, 80, 80);
    scene.add(keyLight);

    const resultGroup = new THREE.Group();
    resultGroup.rotation.set(...(surface.materialPoints ? [0, 0, 0] : [-0.04, -0.34, 0.01]));
    scene.add(resultGroup);

    const meshObject = surface.materialPoints ? new THREE.Points(
      surface.surfaceGeometry,
      new THREE.PointsMaterial({ size: mesh?.pointSize ?? 12, sizeAttenuation: false, vertexColors: true }),
    ) : new THREE.Mesh(
      surface.surfaceGeometry,
      new THREE.MeshStandardMaterial({
        metalness: 0.02,
        roughness: 0.5,
        vertexColors: true,
        side: THREE.DoubleSide,
      }),
    );
    resultGroup.add(meshObject);

    const edges = new THREE.LineSegments(
      surface.lineGeometry,
      new THREE.LineBasicMaterial({ color: 0x020202, transparent: true, opacity: 0.95 }),
    );
    resultGroup.add(edges);

    const toolMeshObject = toolSurface ? new THREE.Mesh(
      toolSurface.surfaceGeometry,
      new THREE.MeshStandardMaterial({
        color: 0xaeb7c3,
        metalness: 0.5,
        roughness: 0.32,
        vertexColors: true,
        side: THREE.DoubleSide,
      }),
    ) : null;
    if (toolMeshObject) {
      resultGroup.add(toolMeshObject);
    }
    const toolEdges = toolSurface ? new THREE.LineSegments(
      toolSurface.lineGeometry,
      new THREE.LineBasicMaterial({ color: 0x1f2937, transparent: true, opacity: 0.22 }),
    ) : null;
    if (toolEdges) {
      resultGroup.add(toolEdges);
    }

    const axisGroup = new THREE.Group();
    scene.add(axisGroup);
    const axisLine = (points, color) => {
      const geometry = new THREE.BufferGeometry().setFromPoints(points.map((point) => new THREE.Vector3(...point)));
      const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color }));
      axisGroup.add(line);
    };

    const center = new THREE.Vector3();
    const size = new THREE.Vector3();
    const viewBounds = framingBounds && !framingBounds.isEmpty() ? framingBounds : surface.bounds;
    viewBounds.getCenter(center);
    viewBounds.getSize(size);
    const modelRadius = Math.max(size.x, size.y, size.z, surface.materialPoints ? 1e-12 : 1);
    const initialDistanceFactor = surface.materialPoints ? 1.75 : 3.15;
    if (surface.materialPoints) { camera.near = modelRadius * 0.001; camera.far = modelRadius * 100; }
    axisGroup.position.set(center.x - modelRadius * 0.65, center.y - modelRadius * 0.34, center.z - modelRadius * 0.62);
    const axisLength = modelRadius * 0.12;
    axisLine([[0, 0, 0], [axisLength, 0, 0]], 0xef4444);
    axisLine([[0, 0, 0], [0, axisLength, 0]], 0x22c55e);
    axisLine([[0, 0, 0], [0, 0, axisLength]], 0x2563eb);

    const savedOrbit = orbitStateRef.current;
    const orbit = savedOrbit ? {
      yaw: toFiniteNumber(savedOrbit.yaw, surface.materialPoints ? 0 : -0.62),
      pitch: toFiniteNumber(savedOrbit.pitch, surface.materialPoints ? 0 : 0.34),
      radius: Math.max(toFiniteNumber(savedOrbit.radius, modelRadius * initialDistanceFactor), modelRadius * 0.2),
      mode: "",
      target: savedOrbit.target instanceof THREE.Vector3 ? savedOrbit.target.clone() : center.clone(),
      x: 0,
      y: 0,
    } : {
      yaw: surface.materialPoints ? 0 : -0.62,
      pitch: surface.materialPoints ? 0 : 0.34,
      radius: modelRadius * initialDistanceFactor,
      mode: "",
      target: center.clone(),
      x: 0,
      y: 0,
    };
    orbitStateRef.current = {
      yaw: orbit.yaw,
      pitch: orbit.pitch,
      radius: orbit.radius,
      target: orbit.target.clone(),
    };

    const saveOrbitState = () => {
      orbitStateRef.current = {
        yaw: orbit.yaw,
        pitch: orbit.pitch,
        radius: orbit.radius,
        target: orbit.target.clone(),
      };
    };

    const updateCamera = () => {
      const pitch = Math.min(Math.max(orbit.pitch, -0.85), 0.95);
      camera.position.set(
        orbit.target.x + Math.sin(orbit.yaw) * Math.cos(pitch) * orbit.radius,
        orbit.target.y + Math.sin(pitch) * orbit.radius,
        orbit.target.z + Math.cos(orbit.yaw) * Math.cos(pitch) * orbit.radius,
      );
      camera.lookAt(orbit.target);
    };

    const onPointerDown = (event) => {
      if (event.button !== 0 && event.button !== 1) {
        return;
      }
      event.preventDefault();
      orbit.mode = event.button === 1 ? "pan" : "rotate";
      orbit.x = event.clientX;
      orbit.y = event.clientY;
      renderer.domElement.style.cursor = orbit.mode === "pan" ? "grabbing" : "move";
      renderer.domElement.setPointerCapture?.(event.pointerId);
    };
    const onPointerMove = (event) => {
      if (!orbit.mode) {
        return;
      }
      event.preventDefault();
      const deltaX = event.clientX - orbit.x;
      const deltaY = event.clientY - orbit.y;
      if (orbit.mode === "pan") {
        const bounds = container.getBoundingClientRect();
        const panScale = (orbit.radius * 1.8) / Math.max(bounds.height, 1);
        const cameraRight = new THREE.Vector3();
        const cameraUp = new THREE.Vector3();
        camera.updateMatrixWorld();
        cameraRight.setFromMatrixColumn(camera.matrixWorld, 0);
        cameraUp.setFromMatrixColumn(camera.matrixWorld, 1);
        orbit.target.addScaledVector(cameraRight, -deltaX * panScale);
        orbit.target.addScaledVector(cameraUp, deltaY * panScale);
      } else {
        orbit.yaw -= deltaX * 0.008;
        orbit.pitch += deltaY * 0.006;
      }
      orbit.x = event.clientX;
      orbit.y = event.clientY;
      saveOrbitState();
    };
    const onPointerUp = (event) => {
      orbit.mode = "";
      renderer.domElement.style.cursor = "grab";
      saveOrbitState();
      if (renderer.domElement.hasPointerCapture?.(event.pointerId)) {
        renderer.domElement.releasePointerCapture?.(event.pointerId);
      }
    };
    const onWheel = (event) => {
      event.preventDefault();
      orbit.radius = Math.min(Math.max(orbit.radius + event.deltaY * (surface.materialPoints ? modelRadius * 0.0018 : 0.18), modelRadius * 1.35), modelRadius * 5.8);
      saveOrbitState();
    };
    const preventDefaultInteraction = (event) => {
      event.preventDefault();
    };

    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerup", onPointerUp);
    renderer.domElement.addEventListener("pointercancel", onPointerUp);
    renderer.domElement.addEventListener("auxclick", preventDefaultInteraction);
    renderer.domElement.addEventListener("contextmenu", preventDefaultInteraction);
    renderer.domElement.addEventListener("wheel", onWheel, { passive: false });
    renderer.domElement.style.cursor = "grab";
    renderer.domElement.style.touchAction = "none";
    renderer.domElement.style.userSelect = "none";

    let frameId = 0;
    const resize = () => {
      const bounds = container.getBoundingClientRect();
      const width = Math.max(1, Math.floor(bounds.width));
      const height = Math.max(1, Math.floor(bounds.height));
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    const animate = () => {
      updateCamera();
      renderer.render(scene, camera);
      frameId = requestAnimationFrame(animate);
    };

    resize();
    window.addEventListener("resize", resize);
    animate();

    return () => {
      saveOrbitState();
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", resize);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("pointercancel", onPointerUp);
      renderer.domElement.removeEventListener("auxclick", preventDefaultInteraction);
      renderer.domElement.removeEventListener("contextmenu", preventDefaultInteraction);
      renderer.domElement.removeEventListener("wheel", onWheel);
      surface.surfaceGeometry.dispose();
      surface.lineGeometry.dispose();
      toolSurface?.surfaceGeometry?.dispose?.();
      toolSurface?.lineGeometry?.dispose?.();
      axisGroup.children.forEach((child) => {
        child.geometry?.dispose?.();
        child.material?.dispose?.();
      });
      meshObject.material.dispose();
      edges.material.dispose();
      toolMeshObject?.material?.dispose?.();
      toolEdges?.material?.dispose?.();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [framingBounds, surface, toolSurface, viewportTheme.background]);

  const handleThemeChange = (themeId) => {
    const nextThemeId = VIEWPORT_THEMES[themeId] ? themeId : "abaqus";
    setViewportThemeId(nextThemeId);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("text-to-cae-viewport-theme", nextThemeId);
    }
  };

  return (
    <div
      className={`relative overflow-hidden rounded-lg border shadow-sm ${fullViewport ? "h-[calc(100svh-1rem)] min-h-[36rem]" : "min-h-[34rem]"}`}
      style={{ background: viewportTheme.cssBackground, borderColor: viewportTheme.border }}
    >
      <div ref={containerRef} className="absolute inset-0" />
      <div
        className="pointer-events-none absolute inset-x-0 top-0 border-b px-4 py-1 text-center text-sm font-semibold"
        style={{ backgroundColor: viewportTheme.header, borderColor: viewportTheme.border, color: viewportTheme.text }}
      >
        {mesh?.representation === "material-points" ? "Peridigm material points — " : text.titlePrefix} {project?.outputs?.odb?.split("/").pop() || mesh?.source || ""}
      </div>

      <div className="pointer-events-auto absolute right-3 top-9 z-10 inline-flex overflow-hidden rounded-md border border-white/25 bg-black/35 text-xs font-semibold text-white shadow-sm">
        {Object.values(VIEWPORT_THEMES).map((theme) => (
          <button
            key={theme.id}
            type="button"
            className={`px-2.5 py-1 transition-colors ${viewportThemeId === theme.id ? "bg-white text-black" : "hover:bg-white/15"}`}
            aria-pressed={viewportThemeId === theme.id}
            onClick={() => handleThemeChange(theme.id)}
          >
            {text.themeLabels[theme.id] || theme.label}
          </button>
        ))}
      </div>

      {modalFrames.length > 1 ? (
        <div className="pointer-events-auto absolute left-1/2 top-9 z-30 flex -translate-x-1/2 items-center gap-1 rounded-md border border-white/25 bg-black/35 px-1.5 py-1 text-xs font-semibold text-white shadow-sm">
          <span className="px-1 text-white/75">{text.modeSelectorLabel}</span>
          {modalFrames.map((mode, index) => (
            <button
              key={`${mode.mode}:${mode.frequencyHz}:${index}`}
              type="button"
              className={`rounded px-2 py-1 transition-colors ${selectedModeIndex === index ? "bg-white text-black" : "hover:bg-white/15"}`}
              aria-pressed={selectedModeIndex === index}
              title={`${text.modalFooterStep} ${mode.mode || index + 1}, ${text.modalFooterFrequency} ${toFiniteNumber(mode.frequencyHz, 0).toFixed(4)} Hz`}
              onClick={() => setSelectedModeIndex(index)}
            >
              {mode.mode || index + 1}
            </button>
          ))}
        </div>
      ) : null}

      {dynamicFrames.length > 1 ? (
        <div className="pointer-events-auto absolute left-1/2 top-9 z-30 flex max-w-[40rem] -translate-x-1/2 items-center gap-1 overflow-hidden rounded-md border border-white/25 bg-black/35 px-1.5 py-1 text-xs font-semibold text-white shadow-sm">
          <button
            type="button"
            className="flex h-7 shrink-0 items-center gap-1 rounded bg-white px-2 text-black transition-colors hover:bg-white/90"
            aria-label={dynamicPlaying ? text.pause : text.play}
            aria-pressed={dynamicPlaying}
            title={dynamicPlaying ? text.pause : text.play}
            onClick={() => setDynamicPlaying((current) => !current)}
          >
            {dynamicPlaying ? <Pause className="size-3.5" aria-hidden="true" /> : <Play className="size-3.5" aria-hidden="true" />}
            <span>{dynamicPlaying ? text.pause : text.play}</span>
          </button>
          <button
            type="button"
            className="flex size-7 shrink-0 items-center justify-center rounded px-1 transition-colors hover:bg-white/15"
            aria-label={text.resetPlayback}
            title={text.resetPlayback}
            onClick={() => {
              setDynamicPlaying(false);
              setSelectedDynamicFrameIndex(0);
            }}
          >
            <RotateCcw className="size-3.5" aria-hidden="true" />
          </button>
          <div className="flex shrink-0 items-center overflow-hidden rounded border border-white/20">
            <span className="px-1.5 text-white/70">{text.speedLabel}</span>
            {[0.5, 1, 2].map((speed) => (
              <button
                key={speed}
                type="button"
                className={`px-1.5 py-1 transition-colors ${dynamicPlaybackSpeed === speed ? "bg-white text-black" : "hover:bg-white/15"}`}
                aria-pressed={dynamicPlaybackSpeed === speed}
                onClick={() => setDynamicPlaybackSpeed(speed)}
              >
                {speed}x
              </button>
            ))}
          </div>
          <span className="shrink-0 px-1 text-white/75">{text.timeSelectorLabel}</span>
          <div className="flex min-w-0 items-center gap-1 overflow-x-auto">
            {dynamicFrames.map((frame, index) => (
              <button
                key={`${frame.frame}:${frame.timeMs}:${index}`}
              type="button"
              className={`shrink-0 rounded px-2 py-1 transition-colors ${selectedDynamicFrameIndex === index ? "bg-white text-black" : "hover:bg-white/15"}`}
              aria-pressed={selectedDynamicFrameIndex === index}
              title={`${text.dynamicFooterStep} ${displayMesh?.step || "Dynamic"} | ${text.dynamicFooterTime} ${toFiniteNumber(frame.timeMs, 0).toFixed(3)} ms`}
                onClick={() => {
                  setDynamicPlaying(false);
                  setSelectedDynamicFrameIndex(index);
                }}
              >
                {mesh?.representation === "material-points" ? `${(toFiniteNumber(frame.timeMs, 0) * 1000).toFixed(1)} μs` : toFiniteNumber(frame.timeMs, 0).toFixed(2)}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {meshError ? (
        <div className="absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-red-200">
          {meshError}
        </div>
      ) : null}

      {!mesh && !meshError ? (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-white/70">
          {text.loading}
        </div>
      ) : null}

      {leftPanel && leftPanelCollapsed ? (
        <button
          type="button"
          className="pointer-events-auto absolute left-3 top-11 z-20 flex h-9 max-w-44 items-center gap-1 rounded-sm border border-[#7f93aa] bg-[#dbe6f1]/95 px-2 text-xs font-semibold text-slate-950 shadow-lg hover:bg-[#e8eef6]"
          aria-label={`${text.expandPanel}: ${leftPanelTitle}`}
          onClick={() => setLeftPanelCollapsed(false)}
        >
          <span aria-hidden="true">&rsaquo;</span>
          <span className="truncate">{leftPanelTitle}</span>
        </button>
      ) : null}

      {leftPanel && !leftPanelCollapsed ? (
        <div className="pointer-events-auto absolute bottom-4 left-3 top-11 z-20 w-56 overflow-hidden rounded-sm border border-[#7f93aa] bg-[#e4ebf3]/95 text-slate-950 shadow-lg">
          <button
            type="button"
            className="absolute right-1 top-1 z-30 flex size-5 items-center justify-center rounded-sm border border-[#8fa4b8] bg-[#d8e4f0] text-xs font-bold text-slate-700 hover:bg-[#eef4fb]"
            aria-label={`${text.collapsePanel}: ${leftPanelTitle}`}
            onClick={() => setLeftPanelCollapsed(true)}
          >
            &lsaquo;
          </button>
          <div className="h-full pr-5">
            {leftPanel}
          </div>
        </div>
      ) : null}

      {rightPanel && rightPanelCollapsed ? (
        <button
          type="button"
          className="pointer-events-auto absolute right-3 top-20 z-20 flex h-9 max-w-44 items-center gap-1 rounded-sm border border-[#7f93aa] bg-[#dbe6f1]/95 px-2 text-xs font-semibold text-slate-950 shadow-lg hover:bg-[#e8eef6]"
          aria-label={`${text.expandPanel}: ${rightPanelTitle}`}
          onClick={() => setRightPanelCollapsed(false)}
        >
          <span className="truncate">{rightPanelTitle}</span>
          <span aria-hidden="true">&lsaquo;</span>
        </button>
      ) : null}

      {rightPanel && !rightPanelCollapsed ? (
        <div className="pointer-events-auto absolute bottom-4 right-3 top-20 z-20 w-72 overflow-hidden rounded-sm border border-[#7f93aa] bg-[#e4ebf3]/95 text-slate-950 shadow-lg">
          <button
            type="button"
            className="absolute left-1 top-1 z-30 flex size-5 items-center justify-center rounded-sm border border-[#8fa4b8] bg-[#d8e4f0] text-xs font-bold text-slate-700 hover:bg-[#eef4fb]"
            aria-label={`${text.collapsePanel}: ${rightPanelTitle}`}
            onClick={() => setRightPanelCollapsed(true)}
          >
            &rsaquo;
          </button>
          <div className="h-full pl-5">
            {rightPanel}
          </div>
        </div>
      ) : null}

      {surface ? (
        <div
          className="pointer-events-none absolute top-20 flex items-start gap-3 text-xs text-white"
          style={{ left: leftPanel && !leftPanelCollapsed ? "16rem" : "1.75rem" }}
        >
          <div className="grid h-44 w-8 overflow-hidden border border-black">
            {[1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0].map((ratio) => (
              <span
                key={ratio}
                style={{ backgroundColor: `#${colorForRatio(ratio).getHexString()}` }}
              />
            ))}
          </div>
          <div className="space-y-[1px] font-mono leading-none">
            <p>{fieldLabel}</p>
            {legendValues.map((value, index) => (
              <p key={`${index}:${value}`}>{formatLegendValue(value)}</p>
            ))}
          </div>
        </div>
      ) : null}

      <div
        className="pointer-events-none absolute bottom-4 text-xs text-white/85"
        style={{
          left: leftPanel && !leftPanelCollapsed ? "16rem" : "1rem",
          right: rightPanel && !rightPanelCollapsed ? "19rem" : "1rem",
        }}
      >
        <p>
          {displayMesh?.representation === "material-points"
            ? `Time: ${toFiniteNumber(displayMesh?.timeMs, 0).toFixed(5)} ms | ${fieldLabel} | displacement scale ${displayMesh?.deformationScale ?? 1} | ${displayMesh?.semantics?.damage || "damage not specified"}`
            : isModalResult
            ? `${text.modalFooterStep} ${displayMesh?.mode || 1} | ${text.modalFooterFrequency} ${toFiniteNumber(displayMesh?.frequencyHz, 0).toFixed(4)} Hz | ${text.modalFooterPrimary} ${toFiniteNumber(displayMesh?.deformationScale, 0).toFixed(1)}`
            : isDynamicResult
              ? `${text.dynamicFooterStep} ${displayMesh?.step || "Dynamic"} | ${text.dynamicFooterTime} ${toFiniteNumber(displayMesh?.timeMs, 0).toFixed(3)} ms | ${text.dynamicFooterPrimary} ${toFiniteNumber(displayMesh?.deformationScale, 0).toFixed(1)}`
            : `${text.footerStep} ${toFiniteNumber(displayMesh?.deformationScale, 0).toFixed(1)}`}
        </p>
        <p>{displayMesh?.representation === "material-points" ? `${displayMesh.nodes.length} material points | no invented FE connectivity | drag to rotate; scroll to zoom` : <>{displayMesh?.nodes?.length || 0} {text.footerMesh} {displayMesh?.elements?.length || 0} {elementType} {text.footerElements}</>}</p>
      </div>
    </div>
  );
}
