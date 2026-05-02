// @stage: mac_rx
// MAC RX: Ethernet frame reception, CRC-32 check, inter-frame gap enforcement
module mac_rx (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  rx_data,
    input  wire        rx_valid,
    input  wire        rx_last,
    output reg  [7:0]  out_data,
    output reg         out_valid,
    output reg         out_last,
    output reg         crc_error
);
    reg [31:0] crc_reg;
    reg [31:0] crc_mem [0:255];  // BRAM: CRC lookup table
    reg [10:0] byte_count;
    reg [3:0]  ifg_count;        // inter-frame gap counter
    wire [31:0] crc_next;

    // CRC pipeline
    assign crc_next = crc_reg ^ (rx_data << 24) ^ (crc_mem[rx_data ^ crc_reg[31:24]]);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            crc_reg    <= 32'hFFFFFFFF;
            byte_count <= 0;
            ifg_count  <= 0;
            out_valid  <= 0;
            crc_error  <= 0;
        end else begin
            if (rx_valid) begin
                crc_reg    <= crc_next;
                byte_count <= byte_count + 1;
                out_data   <= rx_data;
                out_valid  <= 1;
                out_last   <= rx_last;
                if (rx_last) begin
                    crc_error  <= (crc_reg != 32'hC704DD7B);
                    byte_count <= 0;
                    ifg_count  <= 12;
                end
            end else if (ifg_count > 0) begin
                ifg_count <= ifg_count - 1;
                out_valid <= 0;
            end else begin
                out_valid <= 0;
            end
        end
    end

    // CRC init
    integer i;
    always @(posedge clk) begin
        if (!rst_n)
            for (i = 0; i < 256; i = i + 1)
                crc_mem[i] <= i * 32'hEDB88320;
    end

endmodule
