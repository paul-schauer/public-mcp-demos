import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from "@modelcontextprotocol/sdk/types.js";
import axios from "axios";
import * as dotenv from "dotenv";

dotenv.config();

const API_KEY = process.env.USDA_FDC_API_KEY;
if (!API_KEY) {
  console.error("USDA_FDC_API_KEY environment variable not set");
  process.exit(1);
}

const BASE_URL = "https://api.nal.usda.gov/fdc/v1";

class FDCClient {
  private apiKey: string;
  private client = axios.create({ timeout: 30000 });

  constructor(apiKey: string) {
    this.apiKey = apiKey;
  }

  async getFood(fdcId: string, format: string = "full", nutrients?: number[]) {
    const params: any = { api_key: this.apiKey, format };
    if (nutrients) params.nutrients = nutrients.join(",");
    const response = await this.client.get(`${BASE_URL}/food/${fdcId}`, { params });
    return response.data;
  }

  async getFoods(fdcIds: string[], format: string = "full", nutrients?: number[]) {
    if (fdcIds.length > 20) throw new Error("Maximum of 20 FDC IDs allowed");
    const params = { api_key: this.apiKey };
    const data: any = { fdcIds: fdcIds.map(id => parseInt(id)), format };
    if (nutrients) data.nutrients = nutrients;
    const response = await this.client.post(`${BASE_URL}/foods`, data, { params });
    return response.data;
  }

  async searchFoods(query: string, options: {
    dataType?: string[];
    pageSize?: number;
    pageNumber?: number;
    sortBy?: string;
    sortOrder?: string;
    brandOwner?: string;
  } = {}) {
    const params = { api_key: this.apiKey };
    const data: any = { query, pageSize: Math.min(options.pageSize || 50, 200), pageNumber: options.pageNumber || 1 };
    if (options.dataType) data.dataType = options.dataType;
    if (options.sortBy) data.sortBy = options.sortBy;
    if (options.sortOrder) data.sortOrder = options.sortOrder;
    if (options.brandOwner) data.brandOwner = options.brandOwner;
    const response = await this.client.post(`${BASE_URL}/foods/search`, data, { params });
    return response.data;
  }

  async listFoods(options: {
    dataType?: string[];
    pageSize?: number;
    pageNumber?: number;
    sortBy?: string;
    sortOrder?: string;
  } = {}) {
    const params = { api_key: this.apiKey };
    const data: any = { pageSize: Math.min(options.pageSize || 50, 200), pageNumber: options.pageNumber || 1 };
    if (options.dataType) data.dataType = options.dataType;
    if (options.sortBy) data.sortBy = options.sortBy;
    if (options.sortOrder) data.sortOrder = options.sortOrder;
    const response = await this.client.post(`${BASE_URL}/foods/list`, data, { params });
    return response.data;
  }
}

const fdcClient = new FDCClient(API_KEY);

const server = new Server(
  {
    name: "usda-fdc-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "get_food",
        description: "Get details for a single food item by FDC ID.",
        inputSchema: {
          type: "object",
          properties: {
            fdc_id: { type: "string", description: "The FDC ID of the food item" },
            format_type: { type: "string", enum: ["abridged", "full"], default: "full", description: "Format of the response" },
            nutrients: { type: "array", items: { type: "integer" }, description: "List of nutrient IDs to include" }
          },
          required: ["fdc_id"]
        }
      },
      {
        name: "get_foods",
        description: "Get details for multiple food items by FDC IDs.",
        inputSchema: {
          type: "object",
          properties: {
            fdc_ids: { type: "array", items: { type: "string" }, description: "List of FDC IDs" },
            format_type: { type: "string", enum: ["abridged", "full"], default: "full" },
            nutrients: { type: "array", items: { type: "integer" } }
          },
          required: ["fdc_ids"]
        }
      },
      {
        name: "search_foods",
        description: "Search for foods using keywords.",
        inputSchema: {
          type: "object",
          properties: {
            query: { type: "string", description: "Search query" },
            data_type: { type: "array", items: { type: "string" }, description: "Data types to search" },
            page_size: { type: "integer", default: 50, minimum: 1, maximum: 200 },
            page_number: { type: "integer", default: 1, minimum: 1 },
            sort_by: { type: "string" },
            sort_order: { type: "string", enum: ["asc", "desc"] },
            brand_owner: { type: "string" }
          },
          required: ["query"]
        }
      },
      {
        name: "list_foods",
        description: "Get a paged list of foods.",
        inputSchema: {
          type: "object",
          properties: {
            data_type: { type: "array", items: { type: "string" } },
            page_size: { type: "integer", default: 50, minimum: 1, maximum: 200 },
            page_number: { type: "integer", default: 1, minimum: 1 },
            sort_by: { type: "string" },
            sort_order: { type: "string", enum: ["asc", "desc"] }
          }
        }
      }
    ]
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "get_food":
        const result1 = await fdcClient.getFood(args.fdc_id, args.format_type, args.nutrients);
        return { content: [{ type: "text", text: JSON.stringify(result1) }] };

      case "get_foods":
        const result2 = await fdcClient.getFoods(args.fdc_ids, args.format_type, args.nutrients);
        return { content: [{ type: "text", text: JSON.stringify(result2) }] };

      case "search_foods":
        const result3 = await fdcClient.searchFoods(args.query, {
          dataType: args.data_type,
          pageSize: args.page_size,
          pageNumber: args.page_number,
          sortBy: args.sort_by,
          sortOrder: args.sort_order,
          brandOwner: args.brand_owner
        });
        return { content: [{ type: "text", text: JSON.stringify(result3) }] };

      case "list_foods":
        const result4 = await fdcClient.listFoods({
          dataType: args.data_type,
          pageSize: args.page_size,
          pageNumber: args.page_number,
          sortBy: args.sort_by,
          sortOrder: args.sort_order
        });
        return { content: [{ type: "text", text: JSON.stringify(result4) }] };

      default:
        throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`);
    }
  } catch (error) {
    throw new McpError(ErrorCode.InternalError, `Tool execution failed: ${error.message}`);
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("USDA FDC MCP server running on stdio");
}

main().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});