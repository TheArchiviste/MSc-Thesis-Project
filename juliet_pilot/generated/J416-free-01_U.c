#include "std_testcase.h"
#include <wchar.h>
void case_entry(void)
{
    char * data;
    data = NULL;
    data = (char *)malloc(100*sizeof(char));
    if (data == NULL) {exit(-1);}
    memset(data, 'A', 100-1);
    data[100-1] = '\0';
    free(data);
    printLine(data);
}

int main(void)
{
    case_entry();
    return 0;
}
