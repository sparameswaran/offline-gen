#!/bin/bash

TILE_DIRECTORY_PATH=$1
TILE_FILE_PATH=`find $TILE_DIRECTORY_PATH -name *.pivotal | sort | head -1`
tile_metadata=$(unzip -l $TILE_FILE_PATH | grep "metadata" | grep "ml$" | awk '{print $NF}' );
stemcell_version_reqd=$(unzip -p $TILE_FILE_PATH $tile_metadata | grep -A4 stemcell | grep "version:"  | grep -Ei "[0-9]{4,}" | awk '{print $NF}' | sed -e "s/'//g"  );
pivnet-cli login --api-token=$PIVNET_API_TOKEN
pivnet-cli download-product-files -p "stemcells" -r $stemcell_version_reqd -g "*${IAAS}*" --accept-eula
if [ $? != 0 ]; then
 min_version=$(echo $stemcell_version_reqd | awk -F '.' '{print $2}')
 if [ "$min_version" == "" ]; then
   for min_version in $(seq 0  100)
   do
      pivnet-cli download-product-files -p "stemcells" -r $stemcell_version_reqd.$min_version -g "*${IAAS}*" --accept-eula && break
   done
 else
   echo "Stemcell version $stemcell_version_reqd not found !!, giving up"
   exit 1
 fi
fi
