<script setup lang="ts">
/**
 * 知识图谱可视化页面 (Phase 6)
 *
 * - ECharts graph force 力导向画布: 实体(蓝)/文档(橙)/分类(青) 三类节点 + 四类关系边
 * - 搜索实体 → 子图; 重置 → 全景; 节点点击 → 抽屉详情 (关联实体 + 提及文档)
 * - 抽屉内"展开关联"把邻居并入画布; admin 可触发全量重建图谱
 * - 配色: 参考色板 categorical 前三槽位 (all-pairs 校验通过), 边用中性基线色,
 *   节点全部直连标签 (aqua 对比度救济规则)
 */
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { GraphChart } from "echarts/charts";
import { LegendComponent, TooltipComponent } from "echarts/components";
import type { EChartsCoreOption } from "echarts/core";
import VChart from "vue-echarts";
import {
  buildGraphApi,
  getGraphEntityDetailApi,
  getGraphSearchApi,
} from "@/api/graph";
import { useAuthStore } from "@/stores";
import type {
  EntityDetail,
  GraphEdge,
  GraphNode,
  GraphSearchResponse,
} from "@/types/graph";

use([CanvasRenderer, GraphChart, LegendComponent, TooltipComponent]);

const authStore = useAuthStore();

// ==========================================
// 节点分类与画布样式 (参考色板 categorical 前三槽位)
// ==========================================

const NODE_CATEGORIES = [
  { name: "实体", itemStyle: { color: "#2a78d6" } }, // slot 1 blue
  { name: "文档", itemStyle: { color: "#eb6834" } }, // slot 2 orange
  { name: "分类", itemStyle: { color: "#1baf7a" } }, // slot 3 aqua
];
const NODE_CATEGORY_INDEX: Record<string, number> = {
  Entity: 0,
  Document: 1,
  Category: 2,
};
// 边: 中性基线色 (不引入第 4 色, 边类型由 tooltip/抽屉传达)
const EDGE_COLOR = "#c3c2b7";
// 节点标签: 文本用墨色 token, 不用系列色
const LABEL_COLOR = "#52514e";

interface ChartNode {
  id: string;
  name: string;
  category: number;
  symbolSize: number;
  raw: GraphNode;
}

interface ChartEdge {
  source: string;
  target: string;
  value: string;
  raw: GraphEdge;
}

// ==========================================
// 状态
// ==========================================

const keyword = ref("");
const loading = ref(false);
const nodes = ref<ChartNode[]>([]);
const edges = ref<ChartEdge[]>([]);
const stats = ref<GraphSearchResponse["stats"] | null>(null);
const truncated = ref(false);
const chartHeight = ref(640);

// ==========================================
// 数据转换
// ==========================================

function toChartNode(node: GraphNode): ChartNode {
  return {
    id: node.id,
    name: node.label,
    category: NODE_CATEGORY_INDEX[node.node_type] ?? 0,
    // 实体按提及次数放大 (封顶 60), 文档/分类固定
    symbolSize:
      node.node_type === "Entity"
        ? Math.min(60, 18 + (node.mention_count ?? 1) * 6)
        : node.node_type === "Document"
          ? 30
          : 24,
    raw: node,
  };
}

function toChartEdge(edge: GraphEdge): ChartEdge {
  return {
    source: edge.source,
    target: edge.target,
    value: edge.edge_type,
    raw: edge,
  };
}

// ==========================================
// ECharts option
// ==========================================

const option = computed<EChartsCoreOption>(() => ({
  tooltip: {
    formatter: (params: { dataType?: string; data?: ChartNode | ChartEdge }) => {
      if (params.dataType === "edge") {
        const edge = params.data as ChartEdge;
        const detail =
          edge.raw.edge_type === "SIMILAR_TO"
            ? `相似度 ${edge.raw.score ?? "-"}`
            : edge.raw.edge_type === "MENTIONS"
              ? `提及 ${edge.raw.count ?? "-"} 次`
              : edge.raw.edge_type === "RELATED_TO"
                ? `关系: ${edge.raw.relation_type ?? "-"}`
                : "归属分类";
        return `${edge.source} → ${edge.target}<br/>${edge.raw.edge_type} · ${detail}`;
      }
      const node = (params.data as ChartNode).raw;
      const typeText = node.node_type === "Entity" ? node.type ?? "" : node.node_type;
      return `${node.label}${typeText ? `（${typeText}）` : ""}`;
    },
  },
  legend: {
    data: NODE_CATEGORIES.map((c) => c.name),
    top: 8,
    icon: "circle",
  },
  series: [
    {
      type: "graph",
      layout: "force",
      roam: true,
      draggable: true,
      categories: NODE_CATEGORIES,
      data: nodes.value,
      links: edges.value,
      force: {
        repulsion: 260,
        edgeLength: [60, 160],
        gravity: 0.08,
      },
      label: { show: true, position: "right", fontSize: 11, color: LABEL_COLOR },
      lineStyle: { color: EDGE_COLOR, width: 1, curveness: 0.12 },
      emphasis: { focus: "adjacency", lineStyle: { width: 2 } },
    },
  ],
}));

// ==========================================
// 数据加载
// ==========================================

function applyData(data: GraphSearchResponse) {
  nodes.value = data.nodes.map(toChartNode);
  edges.value = data.edges.map(toChartEdge);
  stats.value = data.stats;
  truncated.value = data.truncated;
}

async function loadOverview() {
  loading.value = true;
  try {
    const res = await getGraphSearchApi();
    applyData(res.data);
  } finally {
    loading.value = false;
  }
}

async function handleSearch() {
  const kw = keyword.value.trim();
  if (!kw) {
    await loadOverview();
    return;
  }
  loading.value = true;
  try {
    const res = await getGraphSearchApi(kw);
    applyData(res.data);
    if (!res.data.nodes.length) {
      ElMessage.info("未找到匹配实体");
    }
  } finally {
    loading.value = false;
  }
}

// ==========================================
// 节点点击 → 抽屉详情
// ==========================================

const drawerVisible = ref(false);
const drawerLoading = ref(false);
const detail = ref<EntityDetail | null>(null);

/** ECharts 点击事件参数 (data 为 OptionDataItem 联合类型, 用 unknown 接后再收窄) */
async function handleNodeClick(params: { dataType?: string; data?: unknown }) {
  if (params.dataType !== "node") return;
  const data = params.data as ChartNode | undefined;
  const raw = data?.raw;
  if (!raw) return;
  if (raw.node_type !== "Entity") {
    ElMessage.info(
      raw.node_type === "Document" ? `文档: ${raw.label}` : `分类: ${raw.label}`
    );
    return;
  }
  drawerVisible.value = true;
  drawerLoading.value = true;
  try {
    // Entity 节点的画布 id 即实体名
    const res = await getGraphEntityDetailApi(raw.id);
    detail.value = res.data;
  } finally {
    drawerLoading.value = false;
  }
}

/** 抽屉内"展开关联": 把详情中实体的邻居并入画布 */
function expandNeighbors() {
  if (!detail.value) return;
  const existingIds = new Set(nodes.value.map((n) => n.id));
  for (const neighbor of detail.value.neighbors) {
    if (!existingIds.has(neighbor.name)) {
      nodes.value.push(
        toChartNode({
          id: neighbor.name,
          node_type: "Entity",
          label: neighbor.name,
          type: neighbor.type,
          description: neighbor.description,
          aliases: neighbor.aliases,
          mention_count: 1,
        })
      );
      existingIds.add(neighbor.name);
    }
    const forward = `${detail.value.name}|${neighbor.name}`;
    const backward = `${neighbor.name}|${detail.value.name}`;
    const exists = edges.value.some(
      (e) => `${e.source}|${e.target}` === forward || `${e.source}|${e.target}` === backward
    );
    if (!exists) {
      edges.value.push(
        toChartEdge({
          source: detail.value.name,
          target: neighbor.name,
          edge_type: "RELATED_TO",
          relation_type: neighbor.relation_type,
          weight: neighbor.weight,
        })
      );
    }
  }
}

// ==========================================
// admin 重建图谱
// ==========================================

async function handleRebuild() {
  try {
    await ElMessageBox.confirm(
      "重建图谱将调用 LLM 重新抽取全部已完成向量化文档的实体，耗时较长，确定继续？",
      "图谱重建确认",
      { type: "warning" }
    );
  } catch {
    return; // 用户取消
  }
  const res = await buildGraphApi();
  ElMessage.success(`${res.msg || "重建任务已下发"}，可稍后点击"重置全景"查看最新图谱`);
}

onMounted(loadOverview);
</script>

<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">知识图谱</span>
          <div class="header-actions">
            <el-input
              v-model="keyword"
              placeholder="搜索实体 (如: 年假)"
              clearable
              style="width: 280px"
              @keyup.enter="handleSearch"
            />
            <el-button type="primary" :loading="loading" @click="handleSearch">
              搜索
            </el-button>
            <el-button @click="loadOverview">重置全景</el-button>
            <el-button
              v-if="authStore.isAdmin"
              type="warning"
              plain
              @click="handleRebuild"
            >
              重建图谱
            </el-button>
          </div>
        </div>
      </template>

      <div class="graph-stats" v-if="stats">
        <span>实体 {{ stats.entity_count }}</span>
        <span>文档 {{ stats.document_count }}</span>
        <span>分类 {{ stats.category_count }}</span>
        <span>关系 {{ stats.related_to_count + stats.mentions_count + stats.similar_to_count }}</span>
        <el-tag v-if="truncated" size="small" type="info">节点数达上限已截断</el-tag>
      </div>

      <div class="graph-canvas" v-loading="loading">
        <v-chart
          v-if="nodes.length"
          :option="option"
          autoresize
          :style="{ height: chartHeight + 'px' }"
          @click="handleNodeClick"
        />
        <el-empty
          v-else-if="!loading"
          description="图谱暂无数据 — 文档向量化完成后将自动抽取实体，或由管理员触发重建"
        />
      </div>
    </el-card>

    <el-drawer
      v-model="drawerVisible"
      :title="detail?.name ?? '实体详情'"
      size="380px"
    >
      <div v-loading="drawerLoading">
        <template v-if="detail">
          <p><b>类型：</b>{{ detail.type }}</p>
          <p><b>别名：</b>{{ detail.aliases.join(" / ") || "-" }}</p>
          <p><b>描述：</b>{{ detail.description || "-" }}</p>
          <p><b>被提及：</b>{{ detail.mention_count }} 次</p>

          <el-divider>关联实体（{{ detail.neighbors.length }}）</el-divider>
          <el-table :data="detail.neighbors" size="small" max-height="260">
            <el-table-column prop="name" label="实体" show-overflow-tooltip />
            <el-table-column prop="relation_type" label="关系" width="90" />
            <el-table-column prop="weight" label="权重" width="70" />
          </el-table>
          <el-button
            type="primary"
            plain
            size="small"
            class="expand-btn"
            @click="expandNeighbors"
          >
            展开关联
          </el-button>

          <el-divider>提及文档（{{ detail.documents.length }}）</el-divider>
          <ul class="mention-docs">
            <li v-for="doc in detail.documents" :key="doc.document_id">
              {{ doc.title }}
              <span class="muted">（提及 {{ doc.count }} 次）</span>
            </li>
          </ul>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.page-container {
  padding: @spacing-md;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;

  .card-title {
    font-size: 16px;
    font-weight: 600;
    color: @text-primary;
  }

  .header-actions {
    display: flex;
    gap: @spacing-sm;
  }
}

.graph-stats {
  display: flex;
  align-items: center;
  gap: @spacing-lg;
  margin-bottom: @spacing-sm;
  color: @text-secondary;
  font-size: 13px;
}

.graph-canvas {
  min-height: 320px;
}

.expand-btn {
  margin-top: @spacing-sm;
}

.mention-docs {
  margin: 0;
  padding-left: @spacing-lg;

  li {
    line-height: 1.8;
  }

  .muted {
    color: @text-secondary;
    font-size: 12px;
  }
}
</style>
