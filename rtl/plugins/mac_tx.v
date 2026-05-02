// @stage: mac_tx
// MAC TX: checksum recalculation, frame serialization, egress queue
module mac_tx (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  in_data,
    input  wire        in_valid,
    input  wire        in_last,
    input  wire [31:0] next_hop,
    input  wire [7:0]  out_port,
    output reg  [7:0]  tx_data,
    output reg         tx_valid,
    output reg         tx_last,
    output reg         tx_ready
);
    reg [7:0]  tx_buf  [0:8191]; // BRAM: 8KB TX buffer (jumbo frame support)
    reg [12:0] wr_ptr;
    reg [12:0] rd_ptr;
    reg [12:0] pkt_end;
    reg [15:0] checksum;
    reg        sending;
    reg [1:0]  state;

    localparam IDLE    = 2'd0;
    localparam BUFFER  = 2'd1;
    localparam CKSUM   = 2'd2;
    localparam TRANSMIT= 2'd3;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr   <= 0;
            rd_ptr   <= 0;
            tx_valid <= 0;
            tx_last  <= 0;
            tx_ready <= 1;
            state    <= IDLE;
            checksum <= 0;
        end else begin
            case (state)
                IDLE: begin
                    tx_valid <= 0;
                    if (in_valid) begin
                        state  <= BUFFER;
                        wr_ptr <= 0;
                    end
                end

                BUFFER: begin
                    if (in_valid) begin
                        tx_buf[wr_ptr] <= in_data;
                        checksum       <= checksum + in_data;
                        wr_ptr         <= wr_ptr + 1;
                        if (in_last) begin
                            pkt_end <= wr_ptr;
                            state   <= CKSUM;
                        end
                    end
                end

                CKSUM: begin
                    // Write checksum to fixed offset (IPv4 header checksum at byte 24)
                    tx_buf[24] <= checksum[15:8];
                    tx_buf[25] <= checksum[7:0];
                    checksum   <= 0;
                    rd_ptr     <= 0;
                    state      <= TRANSMIT;
                end

                TRANSMIT: begin
                    tx_data  <= tx_buf[rd_ptr];
                    tx_valid <= 1;
                    rd_ptr   <= rd_ptr + 1;
                    if (rd_ptr >= pkt_end) begin
                        tx_last <= 1;
                        state   <= IDLE;
                    end else begin
                        tx_last <= 0;
                    end
                end
            endcase
        end
    end

endmodule
