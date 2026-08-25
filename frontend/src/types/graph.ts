/**
 * 知识图谱模块类型定义 (Phase 6)
 * 实体 / 画布节点边 / 搜索全景 / 图谱构建
 */

// ==========================================
// 实体
// ==========================================

/** 实体列表项 (GET /graph/entities/) */
export interface EntityListItem {
  name: string;
  type: string;
  description: string;
  aliases: string[];
  mention_count: number;
}

/** 实体关联邻居 (RELATED_TO 一跳) */
export interface EntityNeighbor {
  name: string;
  type: string;
  description: string;
  aliases: string[];
  relation_type: string;
  weight: number;
}

/** 提及该实体的文档 */
export interface EntityMentionDoc {
  document_id: number;
  title: string;
  file_name: string;
  count: number;
  positions: number[];
}

/** 实体详情 (GET /graph/entities/{name}) */
export interface EntityDetail extends EntityListItem {
  neighbors: EntityNeighbor[];
  documents: EntityMentionDoc[];
}

// ==========================================
// 画布 / 搜索 (GET /graph/search)
// ==========================================

/** 统一图节点: Entity(id=name) / Document(id=doc_{id}) / Category(id=cat_{id}) */
export interface GraphNode {
  id: string;
  node_type: "Entity" | "Document" | "Category";
  label: string;
  type?: string;
  description?: string;
  aliases?: string[];
  mention_count?: number;
  document_id?: number;
  title?: string;
  file_name?: string;
  category_id?: number;
  category_name?: string;
}

/** 统一图边 */
export interface GraphEdge {
  source: string;
  target: string;
  edge_type: "RELATED_TO" | "MENTIONS" | "BELONGS_TO" | "SIMILAR_TO";
  relation_type?: string;
  weight?: number;
  count?: number;
  score?: number;
}

/** 图谱统计 (按响应内实际数据计数) */
export interface GraphStats {
  entity_count: number;
  document_count: number;
  category_count: number;
  related_to_count: number;
  mentions_count: number;
  similar_to_count: number;
}

/** 图谱搜索/画布全景统一返回 */
export interface GraphSearchResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
  truncated: boolean;
}
