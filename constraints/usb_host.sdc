# BL616 requested 20 MHz can be 26.667 MHz: constrain for the actual rate.
create_clock -name companion_spi -period 37.500 [get_ports {companion_sck}]
set_clock_groups -asynchronous -group [get_clocks {companion_spi}] -group [get_clocks {clk_27mhz pixel_clk sdram_clk}]
# Mode 1: master changes MOSI on rising edge, FPGA captures falling edge.
set_input_delay -clock [get_clocks {companion_spi}] -max 4.0 [get_ports {companion_mosi}]
set_input_delay -clock [get_clocks {companion_spi}] -min 0.0 [get_ports {companion_mosi}]
set_output_delay -clock [get_clocks {companion_spi}] -clock_fall -max 4.0 [get_ports {companion_miso}]
set_output_delay -clock [get_clocks {companion_spi}] -clock_fall -min 0.0 [get_ports {companion_miso}]
