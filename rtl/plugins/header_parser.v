// @stage: header_parser
// Header Parser: extract Ethernet/IP/TCP/UDP fields, dispatch by EtherType
module header_parser (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  in_data,
    input  wire        in_valid,
    input  wire        in_last,
    output reg  [31:0] src_ip,
    output reg  [31:0] dst_ip,
    output reg  [15:0] src_port,
    output reg  [15:0] dst_port,
    output reg  [7:0]  protocol,
    output reg  [2:0]  ip_version,
    output reg         out_valid,
    output reg         parse_error
);
    reg [7:0]  hdr_buf [0:63];   // BRAM: header buffer
    reg [6:0]  hdr_idx;
    reg [15:0] ethertype;
    wire       is_ipv4 = (ethertype == 16'h0800);
    wire       is_ipv6 = (ethertype == 16'h86DD);
    wire       is_vlan = (ethertype == 16'h8100);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            hdr_idx    <= 0;
            out_valid  <= 0;
            parse_error<= 0;
            src_ip     <= 0;
            dst_ip     <= 0;
            src_port   <= 0;
            dst_port   <= 0;
            protocol   <= 0;
            ip_version <= 0;
        end else if (in_valid) begin
            if (hdr_idx < 64)
                hdr_buf[hdr_idx] <= in_data;
            hdr_idx <= hdr_idx + 1;

            if (hdr_idx == 13) begin
                ethertype <= {hdr_buf[12], in_data};
            end

            if (in_last) begin
                if (is_ipv4) begin
                    ip_version <= 4;
                    src_ip  <= {hdr_buf[26], hdr_buf[27], hdr_buf[28], hdr_buf[29]};
                    dst_ip  <= {hdr_buf[30], hdr_buf[31], hdr_buf[32], hdr_buf[33]};
                    protocol<= hdr_buf[23];
                    src_port<= {hdr_buf[34], hdr_buf[35]};
                    dst_port<= {hdr_buf[36], hdr_buf[37]};
                    out_valid  <= 1;
                    parse_error<= 0;
                end else if (is_ipv6) begin
                    ip_version <= 6;
                    out_valid  <= 1;
                    parse_error<= 0;
                end else begin
                    parse_error<= 1;
                    out_valid  <= 0;
                end
                hdr_idx <= 0;
            end
        end
    end

endmodule
