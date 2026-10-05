#include "std_testcase.h"
#include <wchar.h>
#define SRC_STRING "AAAAAAAAAA"
void case_entry(void)
{
    char * data;
    data = NULL;
    data = (char *)malloc((10+1)*sizeof(char));
    if (data == NULL) {exit(-1);}
    {
        char source[10+1] = SRC_STRING;
        strcpy(data, source);
        printLine(data);
        free(data);
    }
}

int main(void)
{
    case_entry();
    return 0;
}
