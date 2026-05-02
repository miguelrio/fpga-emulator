// @stage: fib_lookup
// FIB Lookup: TCAM-style longest-prefix-match for IPv4/IPv6 routing
module fib_lookup (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [127:0] dst_ip,
    input  wire        in_valid,
    input  wire        is_ipv6,
    output reg  [31:0] next_hop,
    output reg  [7:0]  out_port,
    output reg         hit,
    output reg         miss,
    output reg         out_valid
);
    // BRAM: route table (prefix, mask, next_hop, port)
    reg [127:0] prefix_table [0:1023];
    reg [127:0] mask_table   [0:1023];
    reg [31:0]  nexthop_table[0:1023];
    reg [7:0]   port_table   [0:1023];
    reg [9:0]   table_size;

    reg [9:0]   search_idx;
    reg         searching;
    reg [127:0] search_ip;
    reg [9:0]   best_idx;
    reg [7:0]   best_prefix_len;
    reg         found;

    wire [127:0] masked_ip    = search_ip  & mask_table[search_idx];
    wire [127:0] masked_entry = prefix_table[search_idx] & mask_table[search_idx];
    wire         match        = (masked_ip == masked_entry);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            searching  <= 0;
            out_valid  <= 0;
            hit        <= 0;
            miss       <= 0;
            search_idx <= 0;
            table_size <= 17;  // default routes
        end else begin
            if (in_valid && !searching) begin
                search_ip  <= dst_ip;
                search_idx <= 0;
                searching  <= 1;
                found      <= 0;
                best_prefix_len <= 0;
                out_valid  <= 0;
            end

            if (searching) begin
                if (match) begin
                    if (8'(~0 - $clog2(~mask_table[search_idx])) >= best_prefix_len) begin
                        best_prefix_len <= 8'(~0 - $clog2(~mask_table[search_idx]));
                        best_idx        <= search_idx;
                        found           <= 1;
                    end
                end

                if (search_idx >= table_size - 1) begin
                    searching <= 0;
                    out_valid <= 1;
                    if (found) begin
                        next_hop <= nexthop_table[best_idx];
                        out_port <= port_table[best_idx];
                        hit      <= 1;
                        miss     <= 0;
                    end else begin
                        hit  <= 0;
                        miss <= 1;
                    end
                end else begin
                    search_idx <= search_idx + 1;
                end
            end
        end
    end

endmodule
