// Behavioral SPI block_addressing/SDSC model used by the actual firmware integration test.
module sd_spi_model(input wire sck,cs,mosi,output reg miso);
  reg [7:0] disk[0:4194303];reg [7:0] response[0:1023];
  reg [31:0] save_sectors[0:127];
  reg write_allowed;
  reg [7:0] incoming,command_bytes[0:5],send_byte;
  integer bit_count,command_count,read_ptr,write_ptr,mode,index,sector,reads,writes;
  reg idle;integer i;integer block_addressing;reg [31:0] argument;
  initial begin
    block_addressing=!$test$plusargs("sdsc");
    if($test$plusargs("fat32"))begin
      $readmemh("impl/test-fat32.hex",disk);
      $readmemh("impl/test-fat32-save-sectors.hex",save_sectors);
    end else begin
      $readmemh("impl/test-sd.hex",disk);
      $readmemh("impl/test-sd-save-sectors.hex",save_sectors);
    end
    miso=1;bit_count=0;command_count=0;
    read_ptr=0;write_ptr=0;mode=0;idle=1;reads=0;writes=0;incoming=0;
  end
  task enqueue(input [7:0] value);begin response[write_ptr]=value;write_ptr=write_ptr+1;end endtask
  task receive_byte(input [7:0] value);
    integer j;begin
      if(mode==1)begin if(value==254)begin mode=2;index=0;end end
      else if(mode==2)begin
        if(index<512)disk[sector*512+index]=value;
        index=index+1;
        if(index==514)begin mode=0;writes=writes+1;enqueue(5);enqueue(0);enqueue(0);enqueue(255);end
      end
      else if(command_count!=0 || value[7:6]==2'b01)begin
        command_bytes[command_count]=value;command_count=command_count+1;
        if(command_count==6)begin
          command_count=0;argument={command_bytes[1],command_bytes[2],command_bytes[3],command_bytes[4]};
          case(command_bytes[0]&63)
            0:begin idle=1;enqueue(1);end
            8:begin if(block_addressing)begin enqueue(1);enqueue(0);enqueue(0);enqueue(1);enqueue(8'haa);end else enqueue(5);end
            55:enqueue(idle?1:0);
            41:begin idle=0;enqueue(0);end
            58:begin enqueue(0);enqueue(block_addressing?8'hc0:8'h80);enqueue(8'hff);enqueue(8'h80);enqueue(0);end
            16:begin if(argument!=512)$fatal(1,"bad block size");enqueue(0);end
            17:begin
              sector=block_addressing?argument:argument/512;if(sector<0||sector>=8192)$fatal(1,"read outside image");
              reads=reads+1;enqueue(0);enqueue(255);enqueue(254);
              for(j=0;j<512;j=j+1)enqueue(disk[sector*512+j]);enqueue(255);enqueue(255);
            end
            24:begin
              sector=block_addressing?argument:argument/512;
              write_allowed=0;
              for(j=0;j<128;j=j+1)if(sector==save_sectors[j])write_allowed=1;
              if(!write_allowed)$fatal(1,"write outside save files: LBA %0d",sector);
              enqueue(0);mode=1;
            end
            default:begin $display("Unexpected SD command %d",command_bytes[0]&63);enqueue(4);end
          endcase
        end
      end
    end
  endtask
  always @(posedge cs)begin bit_count=0;command_count=0;read_ptr=0;write_ptr=0;mode=0;miso=1;end
  always @(negedge cs)begin miso=1;send_byte=255;end
  always @(posedge sck)if(!cs)begin
    incoming={incoming[6:0],mosi};bit_count=bit_count+1;
    if(bit_count==8)begin bit_count=0;receive_byte(incoming);end
  end
  always @(negedge sck)if(!cs)begin
    if(bit_count==0)begin
      if(read_ptr<write_ptr)begin send_byte=response[read_ptr];read_ptr=read_ptr+1;end
      else begin send_byte=255;read_ptr=0;write_ptr=0;end
    end
    miso=send_byte[7-bit_count];
  end
endmodule
